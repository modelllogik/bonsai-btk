# bonsai-btk

**Drafting and site tools for [Bonsai](https://bonsaibim.org), made for vocational training.**

*BTK stands for* Bautechnischer Konstrukteur *(building design technician), a German
vocational training. Modelllogik is German for model logic.*

> **Status: scaffold.** Nothing to install yet. The first release (0.1.0) brings an
> intersection snap and a dimension chain tool. See [Roadmap](#roadmap).

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

## Principles

- **Few runtime patches.** The tools use Bonsai's API and operators. Where Bonsai has to
  change, we report it upstream instead of patching it here.
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

Not yet. From 0.1.0 on: download the zip from the release, then in Blender
*Edit → Preferences → Get Extensions → ⌄ → Install from Disk…*. Bonsai must be
installed.

## Building the extension yourself

```bash
blender --command extension build --source-dir bonsai_btk --output-dir dist
```

## Licence

Code is GPL-3.0-or-later, as required for a Bonsai extension. Documentation is
CC BY 4.0. The assignment per path is in `REUSE.toml`.

## How this is made

The tools grow in a workshop used in training and are moved here once they work.
They are written with the help of an AI assistant (Claude); every change is reviewed
and tested in Bonsai by the author.
