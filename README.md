# bonsai-btk

**Drafting and site tools for [Bonsai](https://bonsaibim.org), made for vocational training.**

*BTK stands for* Bautechnischer Konstrukteur *(building design technician), a German
vocational training. Modelllogik is German for model logic.*

> **Status:** [0.2.1](https://github.com/modelllogik/bonsai-btk/releases/tag/v0.2.1) writes the
> vertical datum to the IFC; 0.2.0 added the site tools to the drafting tools of 0.1.0.
> See [Roadmap](#roadmap).

## Why

Trainees learn drawing first, then 3D, then properties. If Bonsai does not deliver a
drawing that looks like the plans they know, it ends up in the corner. With a good
drawing it becomes the door through which the *I* in BIM comes in.

This add-on collects tools that close small gaps between Bonsai and the way German
construction drawings are made and taught: snapping like in CAD, dimensions and levels
after DIN 1356, hatching as real lines, and a site model from official open geodata.
Everything is modelled natively in IFC; the add-on adds tools, not a second data model.

It belongs together with [native-ifc-template](https://github.com/modelllogik/native-ifc-template),
which provides the IFC project template and the drawing style.

## Tools

All tools are in the sidebar of the 3D view (key N), tab **BTK**: panel **Dimensions** for
drafting, panel **Site** for the terrain.

### Drafting

The drafting tools work in an active drawing, in IFC Object Mode.

#### Dimension from Points

Creates a dimension chain from snapped element vertices: horizontal, vertical or inclined
(an inclined wall in a plan, a roof slope in a section).

1. Click the button; the mouse moves into the 3D view. Click element vertices.
   Point 1 → point 2 sets the direction; further points are projected onto the
   dimension line and sorted. *M* = next vertex nearby, *Backspace* = remove the last point.
2. *Enter*: the mouse sets side and offset on a 5 mm grid on the sheet, or type the
   offset in mm. Outside the outer face of the walls, the first chain starts from that
   face and every further parallel chain is placed 10 mm beyond the outermost one.
3. *Click* or *Enter* creates the chain with Bonsai's own dimension annotation in the
   active drawing. *Esc* cancels; nothing is created.

When the drawing scale changes, chains made with this tool move sideways so that their
offset on the sheet stays the same.

#### Intersection snap (key S)

While picking points, *S* switches to the intersection of two edges: click one edge, then
another, and the intersection of the two lines (also beyond the edge ends) is taken as
the point. The view shows tracking lines while you do this. This is how you dimension a
point that is not in the drawing, such as the eaves point where the outer face of a wall
meets the outer face of the roof. *Backspace* removes the first edge, *S* switches off.

#### Flip Dimension

Reverses the point order of the selected chains, so the figures turn with it. After
DIN 1356 a chain reads left to right or bottom to top.

### Site

![The Watzmann massif turning into a cardboard model](https://github.com/modelllogik/bonsai-btk/releases/download/v0.2.0/bonsai-btk-0.2.0.gif)

*Watzmann massif, 2 × 2 km at 1 m, 136 layers of 10 m. Geodata: Bayerische
Vermessungsverwaltung – [geodaten.bayern.de](https://geodaten.bayern.de) (CC BY 4.0);
colours from height and slope.*

The site tools build the surroundings of a building from official open geodata, for
teaching and for presentation: from the real terrain to a cardboard model on the table.
Everything they create hangs on one empty, *BTK_Site_Origin*, and can be moved with the
project origin without being computed again.

On top of the panel *Site* you switch between *Terrain* and *Cardboard Model*, show or hide
the orthophoto, trees and meadow, and choose the camera to look through. Below are seven
steps in the order you work; each header shows a tick once the step is done, the fine
settings fold away under *Settings*.

1. **Project Origin:** easting, northing, height and the rotation as abscissa/ordinate,
   read from or written to the IfcMapConversion of the IFC (with true north and the
   vertical datum of the heights, e.g. EPSG:7837 in Germany). Once the
   terrain is built, a mirror check compares its rotation with the one in the IFC.
2. **Terrain:** a digital terrain model (GeoTIFF, Float32) becomes a mesh, optionally with
   the orthophoto on it. The coordinate reference system is read from the file.
3. **Buildings:** select your IFC house and press *Selection as Building*. This tells the
   tools where the house is: trees and meadow underneath disappear, in the cardboard model
   the house sits on its layer, and the cameras aim at it. Terrain, site and other site
   elements are left out even when selected. Below, the surroundings: neighbouring
   buildings from CityGML LoD2, standing on the terrain; those at your own house are hidden.
4. **Vegetation:** trees from a GeoPackage of single trees, or detected from a surface
   model (nDSM/DSM) – on the terrain as spruces, broadleaf trees and shrubs, in the
   cardboard model as model cones; the species are collections, your own models may go in.
   Meadow: grass and stones after the colours of the orthophoto, dense near the camera.
5. **Cardboard Model:** contour lines at a chosen interval, built up as cardboard layers
   with base plate, table, light and camera – the way a site model is built in the workshop.
6. **Cameras:** find an eye-level and an oblique aerial camera whose picture shows no edge
   of the terrain tile, or check the active camera. Without a marked house they aim at
   the 3D cursor.
7. **Terrain to IFC:** a cut-out of the terrain as IfcGeographicElement (TERRAIN) in the
   IfcSite, aligned to grid north with the rotation in the placement.

Saving the IFC while the cardboard model is shown keeps the placements of the house as
they are – the shift onto the layer is for the view only. Move the house in *Terrain*.

## Principles

- **Few runtime patches.** The tools use Bonsai's API and operators. Where Bonsai has to
  change, we report it upstream instead of patching it here. The add-on replaces nothing in Bonsai.
- **Tested versions are named** in every release.
- **English user interface.** German can follow as a translation file.
- **Small releases.** One tool at a time, usable from day one.

## Roadmap

| Release | Content |
|---|---|
| 0.1.0 | **Intersection snap** (key S, two edges, tracking lines like in CAD) and **dimension chain** |
| 0.2.0 | **Site tools:** terrain and orthophoto from GeoTIFF, cardboard contour model, trees, meadow, LoD2 surroundings, cameras, project origin and georeference with the mirror check, terrain as IFC element |
| 0.2.1 | **Vertical datum:** *To IFC* writes it to IfcProjectedCRS.VerticalDatum, *From IFC* reads it; a warning when it is missing |
| later | Hatching as real lines and dimension figures in German notation (post-processing of drawings), level markers, roof pitch |

The site tools read the coordinate reference system from the data. Terrain, orthophoto
and trees from a surface model work with any GeoTIFF in a projected, metric CRS (for
example ETRS89 / UTM); buildings come from CityGML LoD2. So far they have been tested
with open data from Bavaria; single trees can also be read from the Bavarian tree
dataset (LDBV). Reports with data from other regions are welcome.

Open geodata for Bavaria (CC BY 4.0, source: Bayerische Vermessungsverwaltung –
[geodaten.bayern.de](https://geodaten.bayern.de)) come as 1 km tiles. The
tools read one GeoTIFF per layer, so several tiles are merged into one file first, with
QGIS or GDAL for example.

## Install and update

The add-on comes from its own extension repository. You add the address once; after that
Blender installs and updates it like any other extension.

1. *Edit → Preferences → System → Network:* tick **Allow Online Access**.
2. *Edit → Preferences → Get Extensions → Repositories* (top right) → **+** →
   **Add Remote Repository**, with this URL:

   ```
   https://github.com/modelllogik/bonsai-btk/releases/latest/download/index.json
   ```

   Tick *Check for Updates on Startup* if you like.
3. Search for **BTK Tools for Bonsai** in *Get Extensions* and press *Install*.
   Bonsai must be installed and enabled.

**Update:** when a new release is out, *Get Extensions* shows an *Update* button (after
*Check for Updates* in the ⌄ menu, or at start-up). Do not uninstall the old version first.

**Coming from *Install from Disk*?** If you installed an earlier version from a zip, it sits
in the repository *User Default*. Uninstall it there once, **restart Blender**, then install
from the new repository as above. Two copies of the same extension in two repositories get
in each other's way.

**Without online access** (for example in a closed network): download the zip from the
[latest release](https://github.com/modelllogik/bonsai-btk/releases/latest) and use
*Get Extensions → ⌄ → Install from Disk…*. To update, install the newer zip into the
**same** repository and restart Blender; you then have to watch for new releases yourself.

## Building the extension yourself

```bash
blender --command extension build --source-dir bonsai_btk --output-dir dist
```

How a release and its `index.json` are made is described in [RELEASING.md](RELEASING.md).

The geometry that runs without Blender has tests:

```bash
python -m unittest discover -s tests
```

## Licence

Code is GPL-3.0-or-later, as required for a Bonsai extension. Documentation is
CC BY 4.0. The assignment per path is in `REUSE.toml`.

## How this is made

The tools grow in a workshop used in training and are moved here once they work.
They are written with the help of an AI assistant (Claude); every change is reviewed
and tested in Bonsai by the author.
