# bonsai-btk

**Drafting and site tools for [Bonsai](https://bonsaibim.org), made for vocational training.**

*BTK stands for* Bautechnischer Konstrukteur *(building design technician), a German
vocational training. Modelllogik is German for model logic.*

> **Status: 0.1.0 in preparation.** Intersection snap and dimension chain are in the
> repository; the first release follows after testing. See [Roadmap](#roadmap).

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

All tools are in the sidebar of the 3D view (key N), tab **BTK**. They work in an active
drawing, in IFC Object Mode.

### Dimension from Points

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

### Intersection snap (key S)

While picking points, *S* switches to the intersection of two edges: click one edge, then
another, and the intersection of the two lines (also beyond the edge ends) is taken as
the point. The view shows tracking lines while you do this. This is how you dimension a
point that is not in the drawing, such as the eaves point where the outer face of a wall
meets the outer face of the roof. *Backspace* removes the first edge, *S* switches off.

### Flip Dimension

Reverses the point order of the selected chains, so the figures turn with it. After
DIN 1356 a chain reads left to right or bottom to top.

## Principles

- **Few runtime patches.** The tools use Bonsai's API and operators. Where Bonsai has to
  change, we report it upstream instead of patching it here. 0.1.0 replaces nothing in Bonsai.
- **Tested versions are named** in every release.
- **English user interface.** German can follow as a translation file.
- **Small releases.** One tool at a time, usable from day one.

## Roadmap

| Release | Content |
|---|---|
| 0.1.0 | **Intersection snap** (key S, two edges, tracking lines like in CAD) and **dimension chain** |
| 0.2.0 | **Site model** from GeoTIFF terrain and orthophoto, cardboard contour model, trees, project origin and georeference with the mirror check |
| later | Hatching as real lines and dimension figures in German notation (post-processing of drawings), level markers, roof pitch |

The site tools read the coordinate reference system from the data. Terrain, orthophoto
and trees from a surface model work with any GeoTIFF in a projected, metric CRS (for
example ETRS89 / UTM); buildings come from CityGML LoD2. So far they have been tested
with open data from Bavaria; single trees can also be read from the Bavarian tree
dataset (LDBV). Reports with data from other regions are welcome.

## Install

From 0.1.0 on: download the zip from the release, then in Blender
*Edit → Preferences → Get Extensions → ⌄ → Install from Disk…*. Bonsai must be
installed and enabled.

## Building the extension yourself

```bash
blender --command extension build --source-dir bonsai_btk --output-dir dist
```

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
