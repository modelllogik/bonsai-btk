# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading GeoTIFF: georeference from the TIFF tags, pixels through Blender's image loader.

Convention: arrays are stored "south at the bottom" as in Blender (row 0 = south).
World coordinates = map coordinates − scene origin.
"""
import os
import struct

import bpy
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_TYPES = {1: ('B', 1), 2: ('s', 1), 3: ('H', 2), 4: ('I', 4), 5: ('I', 8), 6: ('b', 1),
          7: ('B', 1), 8: ('h', 2), 9: ('i', 4), 10: ('i', 8), 11: ('f', 4), 12: ('d', 8),
          16: ('Q', 8), 17: ('q', 8), 18: ('Q', 8)}


def _read_tags(path):
    tags = {}
    with open(path, 'rb') as f:
        head = f.read(16)
        if head[:2] not in (b'II', b'MM'):
            raise ValueError("not a TIFF file")
        bo = '<' if head[:2] == b'II' else '>'
        big = struct.unpack(bo + 'H', head[2:4])[0] == 43
        off = struct.unpack(bo + 'Q', head[8:16])[0] if big else struct.unpack(bo + 'I', head[4:8])[0]
        f.seek(off)
        if big:
            n = struct.unpack(bo + 'Q', f.read(8))[0]
            esz = 20
        else:
            n = struct.unpack(bo + 'H', f.read(2))[0]
            esz = 12
        raw = f.read(n * esz)
        for k in range(n):
            e = raw[k * esz:(k + 1) * esz]
            if big:
                tag, typ, cnt = struct.unpack(bo + 'HHQ', e[:12])
                valraw = e[12:20]
            else:
                tag, typ, cnt = struct.unpack(bo + 'HHI', e[:8])
                valraw = e[8:12]
            if typ not in _TYPES:
                continue
            fmt, sz = _TYPES[typ]
            total = sz * cnt
            if total <= len(valraw):
                buf = valraw[:total]
            else:
                p = struct.unpack(bo + ('Q' if big else 'I'), valraw[:8 if big else 4])[0]
                cur = f.tell()
                f.seek(p)
                buf = f.read(total)
                f.seek(cur)
            if typ == 2:
                tags[tag] = buf.rstrip(b'\0').decode('latin1', 'replace')
            elif typ in (5, 10):
                v = struct.unpack(bo + fmt * (2 * cnt), buf)
                tags[tag] = [v[2 * i] / v[2 * i + 1] if v[2 * i + 1] else 0.0 for i in range(cnt)]
            else:
                tags[tag] = list(struct.unpack(bo + fmt * cnt, buf))
    return tags


def georef(path):
    """Georeference of a GeoTIFF file (pixel edges, not pixel centres)."""
    t = _read_tags(path)
    W, H = int(t[256][0]), int(t[257][0])
    if 33550 in t and 33922 in t:
        sx, sy = float(t[33550][0]), float(t[33550][1])
        I, J, _K, X, Y, _Z = t[33922][:6]
        left, top = X - I * sx, Y + J * sy
    elif 34264 in t:
        m = t[34264]
        sx, sy, left, top = float(m[0]), float(-m[5]), float(m[3]), float(m[7])
    else:
        raise ValueError(f"{os.path.basename(path)}: no georeference (not a GeoTIFF?)")
    epsg_proj = epsg_geo = None
    pixel_is_point = False
    gk = t.get(34735)
    if gk and len(gk) >= 4:
        for q in range(gk[3]):
            kid, loc, _cnt, val = gk[4 + 4 * q:8 + 4 * q]
            if loc != 0:
                continue
            if kid == 3072 and val not in (0, 32767):
                epsg_proj = val
            elif kid == 2048 and val not in (0, 32767):
                epsg_geo = val
            elif kid == 1025 and val == 2:
                pixel_is_point = True
    if pixel_is_point:
        left -= sx / 2
        top += sy / 2
    nodata = None
    if 42113 in t:
        try:
            nodata = float(t[42113])
        except ValueError:
            pass
    return dict(W=W, H=H, dx=sx, dy=sy, left=left, top=top,
                right=left + W * sx, bottom=top - H * sy,
                epsg=epsg_proj or epsg_geo, nodata=nodata)


def load_image(path, noncolor, check_existing=True):
    img = bpy.data.images.load(path, check_existing=check_existing)
    if noncolor:
        try:
            img.colorspace_settings.name = 'Non-Color'
        except TypeError:
            pass
    return img


class Raster:
    """Elevation raster (south at the bottom) with georeference."""

    def __init__(self, path, keep_image=False):
        self.path = path
        self.info = georef(path)
        # load a separate image (never an existing one, which e.g. a Displace modifier might use)
        img = load_image(path, True, check_existing=False)
        W, H = img.size
        if (W, H) != (self.info['W'], self.info['H']):
            bpy.data.images.remove(img)
            raise ValueError(f"{os.path.basename(path)}: image size does not match the georeference")
        if not img.is_float:
            bpy.data.images.remove(img)
            raise ValueError(f"{os.path.basename(path)}: no floating point elevations (Float32 expected)")
        px = np.empty(W * H * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        A = px.reshape(H, W, 4)[:, :, 0].copy()
        del px
        if not keep_image:
            bpy.data.images.remove(img)
        nd = self.info['nodata']
        bad = ~np.isfinite(A)
        if nd is not None:
            bad |= np.abs(A - nd) < 1e-3
        bad |= A < -1000
        if bad.any():
            A[bad] = np.nanmin(np.where(bad, np.nan, A)) if (~bad).any() else 0.0
        self.A = A
        self.dx = self.info['dx']
        self.dy = self.info['dy']

    # world coordinates of the pixel centres
    def xs(self, ox):
        return self.info['left'] + (np.arange(self.A.shape[1]) + 0.5) * self.dx - ox

    def ys(self, oy):
        return self.info['bottom'] + (np.arange(self.A.shape[0]) + 0.5) * self.dy - oy

    def sample(self, xw, yw, ox, oy):
        """Bilinear elevation at world coordinates."""
        H, W = self.A.shape
        fx = (np.asarray(xw) + ox - self.info['left']) / self.dx - 0.5
        fy = (np.asarray(yw) + oy - self.info['bottom']) / self.dy - 0.5
        fx = np.clip(fx, 0, W - 1.0001)
        fy = np.clip(fy, 0, H - 1.0001)
        j = np.floor(fx).astype(np.int64)
        i = np.floor(fy).astype(np.int64)
        tx, ty = fx - j, fy - i
        A = self.A
        return (A[i, j] * (1 - tx) * (1 - ty) + A[i, j + 1] * tx * (1 - ty)
                + A[i + 1, j] * (1 - tx) * ty + A[i + 1, j + 1] * tx * ty)


_cache = {}


def get_raster(path):
    """Terrain cache (path + modification time)."""
    key = (path, os.path.getmtime(path))
    r = _cache.get(key)
    if r is None:
        _cache.clear()
        r = Raster(path)
        _cache[key] = r
    return r


# ---- filters (without scipy) ----

def gauss(A, sigma):
    if sigma <= 0:
        return A.astype(np.float64)
    r = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    A = A.astype(np.float64)
    P = np.pad(A, ((0, 0), (r, r)), mode='edge')
    A = sum(k[i] * P[:, i:i + A.shape[1]] for i in range(2 * r + 1))
    P = np.pad(A, ((r, r), (0, 0)), mode='edge')
    A = sum(k[i] * P[i:i + A.shape[0], :] for i in range(2 * r + 1))
    return A


def window(A, r, fn):
    if r <= 0:
        return A
    P = np.pad(A, r, mode='edge')
    return fn(sliding_window_view(P, (2 * r + 1, 2 * r + 1)), axis=(-2, -1))
