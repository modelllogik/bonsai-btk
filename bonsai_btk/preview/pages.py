# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTML pages of the preview: drawing, sheet, print.

Plain HTML and JavaScript without libraries; the pages poll the server once a
second (server.py) and reload when the drawing or sheet changed.

Sheet page, how to move things:
- drag a drawing by its blue frame (the view title moves with it), or the view
  title by its own frame (alone); legend and north arrow by theirs
- 5 mm grid (top left corner), Alt = free (0.1 mm); arrow keys 5 mm, with Alt 1 mm
- two guide lines (magenta), only in the browser: dragging one snaps it to edges of
  the drawings; a moved drawing snaps its edges to the guide lines before the grid
- mouse wheel = zoom, Shift+wheel = horizontal, Ctrl+wheel = vertical scroll,
  double click = whole sheet
- Apply writes the new positions to the layout file and builds the sheet again;
  Discard goes back to the positions of the file
"""

GRID_MM = 5.0

_HEAD_CSS = r"""
  html, body { margin: 0; height: 100%; background: #8a8f96; font-family: Arial, sans-serif; }
  #head { position: fixed; top: 0; left: 0; right: 0; height: 26px; background: #2b2f33; color: #eee;
          display: flex; align-items: center; gap: 10px; padding: 0 8px; font-size: 11px; z-index: 2; white-space: nowrap;
          overflow-x: auto; scrollbar-width: none; }
  #head::-webkit-scrollbar { height: 0; }
  #head > * { flex: none; }
  #head b { color: #fff; } #head a { color: #9cc9ff; }
  #area { position: absolute; top: 26px; bottom: 0; left: 0; right: 0; overflow: auto; }
  #msg { position: fixed; bottom: 0; left: 0; right: 0; background: rgba(43,47,51,.92); color: #ddd; font-size: 11px; z-index: 2; cursor: pointer; }
  #msg:hover #msg-head { color: #fff; }
  #msg-head { padding: 4px 8px; cursor: pointer; user-select: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #msg-text { max-height: 35vh; overflow: auto; padding: 0 8px 5px; white-space: pre-wrap; }
  #msg.closed #msg-text { display: none; }
  .warn { color: #ffb347; }
"""

_MESSAGES_JS = r"""
// Message bar: closed it shows one line, a click opens and closes it
const WARN = /OVERLAP|no type|not |Error|changed/i;
let messageList = [];
function messages(list) {
  messageList = list || [];
  const n = messageList.filter(m => WARN.test(m)).length;
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  document.getElementById('msg-text').innerHTML = messageList.map(m => WARN.test(m) ? '<span class="warn">' + esc(m) + '</span>' : esc(m)).join('\n');
  const closed = document.getElementById('msg').classList.contains('closed');
  document.getElementById('msg-head').innerHTML = (closed ? '▸ ' : '▾ ') + 'Messages (' + messageList.length + ')' +
    (n ? ' · <span class="warn">' + n + ' warning' + (n > 1 ? 's' : '') + '</span>' : '') +
    (closed && messageList.length ? ' · ' + esc(messageList[0]) : '');
  // the area ends above the message bar, which would otherwise cover the horizontal scroll bar
  document.getElementById('area').style.bottom = document.getElementById('msg-head').offsetHeight + 'px';
}
document.getElementById('msg').addEventListener('click', () => {
  if (String(window.getSelection() || '')) return;   // text selected: keep it open
  document.getElementById('msg').classList.toggle('closed'); messages(messageList); });
messages([]);
// Shift+wheel = horizontal, Ctrl+wheel = vertical scroll; true if it scrolled
function scrollWheel(e) {
  if (!e.shiftKey && !e.ctrlKey) return false;
  e.preventDefault();
  const f = document.getElementById('area'), d = e.deltaY || e.deltaX;
  if (e.shiftKey) f.scrollLeft += d; else f.scrollTop += d;
  return true;
}
"""

DRAWING_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>BTK Preview</title>
<style>""" + _HEAD_CSS + r"""
  #sheet { background: #fff; margin: 24px auto; box-shadow: 0 2px 10px rgba(0,0,0,.35); display: block; }
</style></head>
<body>
<div id="head"><b>BTK Preview</b><span id="name">-</span><span id="time"></span><a href="/sheet">Sheet</a>
  <span style="margin-left:auto" title="Wheel = zoom · Shift+wheel = horizontal · Ctrl+wheel = vertical · double click = 100 %">Zoom <span id="zoom">100</span>%</span></div>
<div id="area"><img id="sheet" alt=""></div>
<div id="msg" class="closed"><div id="msg-head"></div><div id="msg-text"></div></div>
<script>""" + _MESSAGES_JS + r"""
let seen = 0, factor = 2, base = 0;
const img = document.getElementById('sheet');
function setWidth() { if (base) { img.style.width = (base * factor) + 'px'; document.getElementById('zoom').textContent = Math.round(factor * 100); } }
img.onload = () => { base = img.naturalWidth; setWidth(); };
document.getElementById('area').addEventListener('wheel', e => {
  e.preventDefault(); if (scrollWheel(e)) return; factor = Math.min(20, Math.max(0.2, factor * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); setWidth(); }, {passive: false});
img.addEventListener('dblclick', () => { factor = 1; setWidth(); });
async function poll() {
  try {
    const r = await fetch('/state', {cache: 'no-store'}); const s = await r.json();
    if (s.mtime && s.mtime !== seen) {
      seen = s.mtime;
      img.src = '/drawing.svg?t=' + s.mtime;
      document.getElementById('name').textContent = s.name;
      document.getElementById('time').textContent = 'created ' + s.time;
      messages(s.messages);
    }
  } catch (e) { document.getElementById('time').textContent = 'Blender not reachable'; }
  setTimeout(poll, 1000);
}
poll();
</script></body></html>"""

_PRINT_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>BTK Print Sheet</title>
<style>
  /* page size = sheet size, no margin: the print dialog starts with the right format
     and the scale stays 1:1 */
  @page { size: %WIDTH%mm %HEIGHT%mm; margin: 0; }
  html, body { margin: 0; padding: 0; background: #8a8f96; font-family: Arial, sans-serif; }
  #sheet { display: block; width: %WIDTH%mm; height: %HEIGHT%mm; background: #fff;
           margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,.35); }
  #note { background: #2b2f33; color: #eee; font-size: 12px; line-height: 1.5; padding: 8px 12px; }
  #note b { color: #fff; } #note ul { margin: 6px 0 0 18px; padding: 0; }
  #note .warn { color: #ffb347; }
  button { font: inherit; padding: 2px 10px; margin-left: 10px; border-radius: 3px;
           border: 1px solid #0a6ed1; background: #0a6ed1; color: #fff; cursor: pointer; }
  @media print {
    #note { display: none; }
    html, body { background: #fff; }
    #sheet { box-shadow: none; margin: 0; }
  }
</style></head>
<body>
<div id="note"><b>%NAME%</b> &middot; sheet %WIDTH% &times; %HEIGHT% mm, printed at full size
  <button id="now">Print</button>
  <ul>
    <li>In the print dialog set <b>Margins: None</b> and <b>Scale: Default (100 %)</b>,
        not &ldquo;Fit to page&rdquo;, or the scale will be wrong.</li>
    <li>Headers and footers off.</li>
    <li class="warn">The browser rasterises the hatching. For the real print use PDF on the sheet page.</li>
    <li class="warn">Only a printer that can print borderless prints to the edge; otherwise the scale
        stays right but the outer millimetres of the sheet are missing.</li>
  </ul></div>
<img id="sheet" src="/sheet.svg" alt="Sheet">
<script>
const picture = document.getElementById('sheet');
document.getElementById('now').addEventListener('click', () => window.print());
let done = false;
function printWhenReady() {
  if (done) return;
  done = true;
  setTimeout(() => window.print(), 200);     // give the picture time to build
}
if (picture.complete) printWhenReady(); else picture.addEventListener('load', printWhenReady);
</script></body></html>"""


def _escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def print_page(name, width, height):
    """Print page with the size of the built sheet."""
    return (_PRINT_PAGE.replace("%WIDTH%", "%g" % (width or 420.0))
                       .replace("%HEIGHT%", "%g" % (height or 297.0))
                       .replace("%NAME%", _escape(str(name))))


SHEET_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>BTK Sheet</title>
<style>""" + _HEAD_CSS + r"""
  #frame { margin: 24px auto; box-shadow: 0 2px 10px rgba(0,0,0,.35); background: #fff; display: block; border: 0; }
  button { font: inherit; padding: 1px 7px; border-radius: 3px; border: 1px solid #666; background: #444; color: #eee; cursor: pointer; }
  button.on { background: #0a6ed1; border-color: #0a6ed1; color: #fff; }
  button:disabled { opacity: .45; cursor: default; }
  #where { font-variant-numeric: tabular-nums; flex: 1 1 auto !important; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
</style></head>
<body>
<div id="head"><b>BTK Sheet</b><span id="name">-</span><span id="time"></span><a href="/">Drawing</a>
  <span id="where"></span>
  <button id="guides" class="on" title="Show or hide the vertical and horizontal guide line">Guides</button>
  <button id="discard" disabled>Discard</button>
  <button id="apply" disabled>Apply</button>
  <button id="print" title="Print the sheet at full size in its own tab: page size = sheet size, no margin.&#10;Good for looking at; the browser rasterises the hatching">Print</button>
  <button id="pdf" title="Open the sheet as PDF made by Inkscape: the hatching stays vector, for the real print.&#10;Takes a few seconds">PDF</button>
  <span title="Wheel = zoom · Shift+wheel = horizontal · Ctrl+wheel = vertical · double click = whole sheet">Zoom <span id="zoom">100</span>%</span></div>
<div id="area"><iframe id="frame" title="Sheet" scrolling="no"></iframe></div>
<div id="msg" class="closed"><div id="msg-head"></div><div id="msg-text"></div></div>
<script>""" + _MESSAGES_JS + r"""
// Print in its own tab with page size = sheet size; not from this window, or the head
// and the message bar would come onto the paper.
document.getElementById('print').addEventListener('click', () => window.open('/print', '_blank'));
// PDF through Inkscape: the right way to the printer, as the browser rasterises patterns.
document.getElementById('pdf').addEventListener('click', () => window.open('/sheet/pdf', '_blank'));
const MM = 96 / 25.4, GRID = %GRID%;
const NS = 'http://www.w3.org/2000/svg';
let seen = 0, factor = 1, fitted = false, data = null, doc = null, svg = null;
let pos = {};        // id -> [x, y] of the drawing, as now in the browser
let selected = null, drag = null, waiting = false;
// Guide lines: only in the browser, never in a file. x = vertical line, y = horizontal line (mm)
const SNAP_PX = 8, GUIDE_COLOUR = '#d4148c';
let guide = {on: true, x: null, y: null}, gdrag = null, snap = '';
let guideSize = null;  // sheet size for which the guide lines were last checked
let edges = {};      // id -> {xs, ys}: edges of the drawing geometry in sheet mm, at the layout position
let edgesT = {};     // id -> {xs, ys}: text edges of the view title in sheet mm, at the layout position
let toff = {};       // id -> [dx, dy]: own offset of the title against the drawing
let part = 'drawing'; // selected part: 'drawing' (with title) or 'title' (alone)
const group = id => id === 'legend' ? doc.querySelector('g[data-type="din-legende"]') : id === 'north' ? doc.querySelector('g[data-type="din-nordpfeil"]') : doc.querySelector('g[data-type="drawing"][data-id="' + id + '"]');
const titleAbs = z => [z.title.x + pos[z.id][0] - z.drawing.x + toff[z.id][0], z.title.y + pos[z.id][1] - z.drawing.y + toff[z.id][1]];
const $ = id => document.getElementById(id);
const frame = $('frame');

function setZoom() {
  if (!svg || !data) return;
  const w = data.width * MM * factor, h = data.height * MM * factor;
  svg.setAttribute('width', w + 'px'); svg.setAttribute('height', h + 'px');
  frame.style.width = w + 'px'; frame.style.height = h + 'px';
  $('zoom').textContent = Math.round(factor * 100);
}
function fit() {
  const f = $('area');
  factor = Math.min((f.clientWidth - 48) / (data.width * MM), (f.clientHeight - 80) / (data.height * MM));
}
function zoomWheel(e) { e.preventDefault(); if (scrollWheel(e)) return; factor = Math.min(12, Math.max(0.3, factor * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); setZoom(); }
function toMM(e) { const p = svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); }
const Z = id => data.drawings.find(z => z.id === id);
const changed = () => data.drawings.filter(z => Math.abs(pos[z.id][0] - z.drawing.x) > 1e-6 || Math.abs(pos[z.id][1] - z.drawing.y) > 1e-6
  || Math.abs(toff[z.id][0]) > 1e-6 || Math.abs(toff[z.id][1]) > 1e-6);
const f1 = v => v.toFixed(1);

function show() {
  for (const z of data.drawings) {
    const dx = pos[z.id][0] - z.drawing.x, dy = pos[z.id][1] - z.drawing.y;
    const t = 'translate(' + dx + ' ' + dy + ')';
    const g = group(z.id);
    if (g) g.setAttribute('transform', t);
    const tg = z.title && g && [...g.children].filter(k => k.tagName === 'g')[1];
    if (tg && tg.dataset.dinTransform !== undefined) {
      const m = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)/.exec(tg.dataset.dinTransform);
      if (m) tg.setAttribute('transform', 'translate(' + (+m[1] + toff[z.id][0]) + ',' + (+m[2] + toff[z.id][1]) + ')');
    }
    const handle = doc.getElementById('din-handle-' + z.id);
    handle.setAttribute('transform', t);
    const ht = handle.querySelector('.din-handle-title');
    if (ht) ht.setAttribute('transform', 'translate(' + toff[z.id][0] + ' ' + toff[z.id][1] + ')');
    const sel = z.id === selected;
    for (const r of handle.querySelectorAll('rect')) {
      const on = sel && (part === 'drawing' || r.parentNode.classList.contains('din-handle-title'));
      r.setAttribute('stroke', on ? '#e67e00' : '#0a6ed1');
      r.setAttribute('stroke-dasharray', on ? 'none' : '2 1');
    }
  }
  const n = changed().length;
  $('apply').disabled = !n || waiting; $('discard').disabled = !n || waiting;
  $('apply').className = n && !waiting ? 'on' : '';
  $('apply').textContent = waiting ? 'building sheet …' : (n ? 'Apply (' + n + ')' : 'Apply');
  showGuides();
  if (selected === 'guide-x' || selected === 'guide-y') {
    const vertical = selected === 'guide-x';
    $('where').innerHTML = '<b>Guide line ' + (vertical ? 'vertical</b> · x ' + f1(guide.x) : 'horizontal</b> · y ' + f1(guide.y)) + ' mm' +
      (snap ? ' · <span style="color:#ff7ac8">' + snap + '</span>' : '');
  } else if (selected) {
    const z = Z(selected), x = pos[selected][0], y = pos[selected][1];
    const [tx, ty] = z.title ? titleAbs(z) : [null, null];
    const outside = x < 0 || y < 0 || x + z.drawing.width > data.width || y + z.drawing.height > data.height;
    $('where').innerHTML = '<b>' + z.name + (part === 'title' ? ' – title alone' : '') + '</b> · drawing x ' + f1(x) + ' / y ' + f1(y) + ' mm' +
      (z.title ? ' · title x ' + f1(tx) + ' / y ' + f1(ty) + ' mm' : '') +
      (snap ? ' · <span style="color:#ff7ac8">' + snap + '</span>' : '') +
      (outside ? ' <span class="warn">· reaches over the sheet</span>' : '');
  } else $('where').textContent = 'drawing frame = with title, title frame = title alone · grid ' + GRID + ' mm · snaps to guide lines · Alt = free';
}

function makeHandles() {
  const old = doc.getElementById('din-handles'); if (old) old.remove();
  const gg = doc.createElementNS(NS, 'g'); gg.id = 'din-handles';
  for (const z of data.drawings) {
    const g = doc.createElementNS(NS, 'g'); g.id = 'din-handle-' + z.id; g.setAttribute('data-id', z.id);
    for (const [r, kind] of [[z.drawing, 'drawing'], [z.title, 'title']]) {
      if (!r) continue;
      const sub = doc.createElementNS(NS, 'g'); sub.setAttribute('class', 'din-handle-' + kind);
      const e = doc.createElementNS(NS, 'rect');
      for (const [k, v] of Object.entries({x: r.x, y: r.y, width: r.width, height: r.height, fill: '#0a6ed1',
             'fill-opacity': 0.04, stroke: '#0a6ed1', 'stroke-width': 0.35, 'vector-effect': 'non-scaling-stroke'})) e.setAttribute(k, v);
      e.style.cursor = 'move';
      sub.appendChild(e);
      sub.addEventListener('mouseenter', () => e.setAttribute('fill-opacity', 0.12));
      sub.addEventListener('mouseleave', () => e.setAttribute('fill-opacity', 0.04));
      sub.addEventListener('mousedown', ev => {
        if (waiting) return;
        ev.preventDefault(); ev.stopPropagation(); selected = z.id; part = kind;
        const p = toMM(ev);
        drag = kind === 'title' ? {id: z.id, kind, px: p.x, py: p.y, x0: titleAbs(z)[0], y0: titleAbs(z)[1]}
                                : {id: z.id, kind, px: p.x, py: p.y, x0: pos[z.id][0], y0: pos[z.id][1]};
        show();
      });
      g.appendChild(sub);
    }
    gg.appendChild(g);
  }
  svg.appendChild(gg);
}

function collectEdges() {
  // Axis-parallel edges of every element of a drawing (its bounding box) in sheet mm.
  // Only the drawing itself (first group), not the view title; no texts.
  edges = {};
  const inv = svg.getScreenCTM().inverse();
  for (const z of data.drawings) {
    const g = group(z.id) && group(z.id).querySelector(':scope > g');
    const xs = new Set(), ys = new Set();
    if (g) for (const el of g.querySelectorAll('path, line, polyline, polygon, rect')) {
      if (el.closest('defs, clipPath, marker, pattern, symbol')) continue;
      let bb; try { bb = el.getBBox(); } catch (e) { continue; }
      if (!bb || (bb.width === 0 && bb.height === 0)) continue;
      const m = inv.multiply(el.getScreenCTM());
      const corners = [[bb.x, bb.y], [bb.x + bb.width, bb.y + bb.height]].map(([a, b]) => ({x: m.a * a + m.c * b + m.e, y: m.b * a + m.d * b + m.f}));
      for (const q of corners) { xs.add(Math.round(q.x * 100) / 100); ys.add(Math.round(q.y * 100) / 100); }
    }
    edges[z.id] = {xs: [...xs], ys: [...ys]};
    // Title: outline of the texts; remember the transform, the own offset goes on top of it
    const tg = z.title && group(z.id) && [...group(z.id).children].filter(k => k.tagName === 'g')[1];
    const txs = new Set(), tys = new Set();
    if (tg) {
      tg.dataset.dinTransform = tg.getAttribute('transform') || '';
      for (const el of tg.querySelectorAll('text')) {
        let bb; try { bb = el.getBBox(); } catch (e) { continue; }
        const m = inv.multiply(el.getScreenCTM());
        for (const [a, b] of [[bb.x, bb.y], [bb.x + bb.width, bb.y + bb.height]]) {
          txs.add(Math.round((m.a * a + m.c * b + m.e) * 100) / 100); tys.add(Math.round((m.b * a + m.d * b + m.f) * 100) / 100);
        }
      }
    }
    edgesT[z.id] = {xs: [...txs], ys: [...tys]};
  }
}
const tolMM = () => SNAP_PX / (MM * factor);
function nearest(value, list) {
  let best = null;
  for (const v of list) if (best === null || Math.abs(v - value) < Math.abs(best - value)) best = v;
  return best !== null && Math.abs(best - value) <= tolMM() ? best : null;
}
function showGuides() {
  const g = doc && doc.getElementById('din-guides'); if (!g) return;
  g.style.display = guide.on ? '' : 'none';
  $('guides').className = guide.on ? 'on' : '';
  const put = (id, a) => { for (const l of g.querySelectorAll('.' + id)) for (const [k, v] of Object.entries(a)) l.setAttribute(k, v); };
  put('gx', {x1: guide.x, x2: guide.x, y1: 0, y2: data.height});
  put('gy', {x1: 0, x2: data.width, y1: guide.y, y2: guide.y});
  for (const l of g.querySelectorAll('.seen')) l.setAttribute('stroke-width', (l.classList.contains('gx') ? selected === 'guide-x' : selected === 'guide-y') ? 2 : 1);
}
function fitGuides() {
  // Another sheet: the guide lines keep their place while they are on the new sheet;
  // one that would be outside or on the edge moves to the middle. Between two sheets
  // of the same size everything stays, the zoom too.
  const size = data.width + 'x' + data.height;
  const on = (v, max) => v > 0 && v < max;
  if (guide.x === null) { guide.x = Math.round(data.width / 2); guide.y = Math.round(data.height / 2); }
  else if (guideSize !== size) {
    if (!on(guide.x, data.width)) guide.x = Math.round(data.width / 2);
    if (!on(guide.y, data.height)) guide.y = Math.round(data.height / 2);
    fitted = false;   // other sheet size: fit the zoom again
  }
  guideSize = size;
}
function makeGuides() {
  const old = doc.getElementById('din-guides'); if (old) old.remove();
  const g = doc.createElementNS(NS, 'g'); g.id = 'din-guides';
  for (const [kind, cursor] of [['gx', 'ew-resize'], ['gy', 'ns-resize']]) {
    for (const visible of [true, false]) {
      const l = doc.createElementNS(NS, 'line');
      l.setAttribute('class', kind + (visible ? ' seen' : ' grip'));
      l.setAttribute('vector-effect', 'non-scaling-stroke');
      if (visible) { l.setAttribute('stroke', GUIDE_COLOUR); l.setAttribute('stroke-width', 1); l.setAttribute('pointer-events', 'none'); }
      else {
        l.setAttribute('stroke', '#000'); l.setAttribute('stroke-opacity', 0); l.setAttribute('stroke-width', 9);
        l.setAttribute('pointer-events', 'stroke'); l.style.cursor = cursor;
        l.addEventListener('mousedown', e => {
          if (waiting) return;
          e.preventDefault(); e.stopPropagation(); selected = kind === 'gx' ? 'guide-x' : 'guide-y'; gdrag = kind; snap = ''; show();
        });
      }
      g.appendChild(l);
    }
  }
  svg.appendChild(g);
}
function edgesNow(id, x, y) {
  // edges of drawing id with its top left corner at x/y
  const z = Z(id), k = edges[id] || {xs: [], ys: []};
  return {xs: k.xs.map(v => v + x - z.drawing.x), ys: k.ys.map(v => v + y - z.drawing.y)};
}
function titleEdgesNow(id, x, y) {
  // text edges of the title with the top left corner of the title image at x/y
  const z = Z(id), k = edgesT[id] || {xs: [], ys: []};
  return {xs: k.xs.map(v => v + x - z.title.x), ys: k.ys.map(v => v + y - z.title.y)};
}
function onMove(e) {
  if (gdrag) {
    const p = toMM(e), vertical = gdrag === 'gx';
    let w = vertical ? p.x : p.y; snap = '';
    if (!e.altKey) {
      const all = [];
      for (const z of data.drawings) {
        const k = edgesNow(z.id, pos[z.id][0], pos[z.id][1]); all.push(...(vertical ? k.xs : k.ys));
        if (z.title) { const [tx, ty] = titleAbs(z), kt = titleEdgesNow(z.id, tx, ty); all.push(...(vertical ? kt.xs : kt.ys)); }
      }
      const f = nearest(w, all);
      if (f !== null) { w = Math.round(f * 1000) / 1000; snap = 'at an edge'; }
    }
    if (!snap) w = Math.round(w * 10) / 10;
    if (vertical) guide.x = w; else guide.y = w;
    show(); return;
  }
  if (!drag) return;
  const p = toMM(e);
  const xr = drag.x0 + p.x - drag.px, yr = drag.y0 + p.y - drag.py;
  let x, y; snap = '';
  if (e.altKey) { x = Math.round(xr * 10) / 10; y = Math.round(yr * 10) / 10; }
  else {
    x = Math.round(xr / GRID) * GRID; y = Math.round(yr / GRID) * GRID;
    if (guide.on) {
      const k = drag.kind === 'title' ? titleEdgesNow(drag.id, xr, yr) : edgesNow(drag.id, xr, yr), axes = [];
      const fx = nearest(guide.x, k.xs), fy = nearest(guide.y, k.ys);
      if (fx !== null) { x = xr + guide.x - fx; axes.push('x'); }
      if (fy !== null) { y = yr + guide.y - fy; axes.push('y'); }
      if (axes.length) snap = 'snaps to guide line ' + axes.join(' and ');
    }
  }
  x = Math.round(x * 1000) / 1000; y = Math.round(y * 1000) / 1000;
  if (drag.kind === 'title') {
    const z = Z(drag.id);
    toff[drag.id] = [x - (z.title.x + pos[drag.id][0] - z.drawing.x), y - (z.title.y + pos[drag.id][1] - z.drawing.y)];
  } else pos[drag.id] = [x, y];
  show();
}
function onKey(e) {
  if (!selected || waiting) return;
  const s = e.altKey ? 1 : GRID, d = {ArrowLeft: [-s, 0], ArrowRight: [s, 0], ArrowUp: [0, -s], ArrowDown: [0, s]}[e.key];
  if (d && selected.startsWith('guide-')) {
    e.preventDefault(); const t = e.altKey ? 0.1 : 1; snap = '';
    if (selected === 'guide-x') guide.x = Math.round((guide.x + Math.sign(d[0]) * t) * 10) / 10;
    else guide.y = Math.round((guide.y + Math.sign(d[1]) * t) * 10) / 10;
    show();
  } else if (d && part === 'title') { e.preventDefault(); toff[selected] = [Math.round((toff[selected][0] + d[0]) * 1000) / 1000, Math.round((toff[selected][1] + d[1]) * 1000) / 1000]; show(); }
  else if (d) { e.preventDefault(); pos[selected] = [Math.round((pos[selected][0] + d[0]) * 10) / 10, Math.round((pos[selected][1] + d[1]) * 10) / 10]; show(); }
  if (e.key === 'Escape') { selected = null; show(); }
}

frame.onload = () => {
  doc = frame.contentDocument; svg = doc && doc.documentElement;
  if (!svg || svg.tagName.toLowerCase() !== 'svg') return;
  // No scroll bars at the sheet edge: the frame is the size of the sheet to fractions
  // of a pixel, the document rounds to whole pixels. Scrolling is always outside, in #area.
  try { svg.style.overflow = 'hidden'; } catch (e) {}
  snap = ''; pos = {}; toff = {}; for (const z of data.drawings) { pos[z.id] = [z.drawing.x, z.drawing.y]; toff[z.id] = [0, 0]; }
  fitGuides();
  if (!fitted) { fit(); fitted = true; }
  makeHandles(); setZoom(); collectEdges(); makeGuides(); show();
  doc.addEventListener('mousemove', onMove);
  doc.addEventListener('mouseup', () => { drag = null; gdrag = null; });
  doc.addEventListener('wheel', zoomWheel, {passive: false});
  doc.addEventListener('keydown', onKey);
  doc.addEventListener('dblclick', e => { if (e.target.closest && e.target.closest('#din-handles')) return; fit(); setZoom(); });
  doc.addEventListener('mousedown', e => { if (!e.target.closest || !e.target.closest('#din-handles, #din-guides')) { selected = null; snap = ''; show(); } });
};
document.addEventListener('keydown', onKey);
document.addEventListener('mouseup', () => { drag = null; gdrag = null; });
$('guides').onclick = () => { guide.on = !guide.on; if (!guide.on && selected && selected.startsWith('guide-')) selected = null; show(); };
$('area').addEventListener('wheel', zoomWheel, {passive: false});

$('discard').onclick = () => { for (const z of data.drawings) { pos[z.id] = [z.drawing.x, z.drawing.y]; toff[z.id] = [0, 0]; } show(); };
$('apply').onclick = async () => {
  const change = {}; for (const z of changed()) change[z.id] = {drawing: pos[z.id], title: z.title ? titleAbs(z) : null};
  waiting = true; show();
  try {
    const r = await fetch('/sheet/apply', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({layout_sha: data.layout_sha, positions: change})});
    const s = await r.json();
    if (!r.ok) { waiting = false; messages(['Error: ' + s.error]); document.getElementById('msg').classList.remove('closed'); messages(messageList); show(); }
  } catch (e) { waiting = false; messages(['Error: Blender not reachable']); show(); }
};

async function poll() {
  try {
    const r = await fetch('/sheet/state', {cache: 'no-store'}); const s = await r.json();
    if (s.mtime && s.mtime !== seen) {
      seen = s.mtime; data = s; waiting = false;
      frame.src = '/sheet.svg?t=' + s.mtime;
      $('name').textContent = s.name; $('time').textContent = 'built ' + s.time;
      messages(s.messages);
    } else if (waiting && !s.building) { waiting = false; messages(s.messages); show(); }
  } catch (e) { $('time').textContent = 'Blender not reachable'; }
  setTimeout(poll, 1000);
}
poll();
</script></body></html>""".replace("%GRID%", repr(GRID_MM))
