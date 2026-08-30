# PXCOMP

PXCOMP is a Windows desktop image compositor for combining a sequence of photographs through mutually exclusive spatial ownership.

## Core rule

For `N` source photographs, every output coordinate belongs to exactly one source. Integer pixel quotas are equal to within one pixel when the canvas pixel count is not divisible by `N`.

That guarantees:

- **100% canvas coverage**
- **0% overlap between source masks**
- **0 unassigned pixels**
- deterministic reconstruction from project seed, algorithm version, parameters, and source transforms

## Allocation modes

### Pixel Random

Every coordinate is randomly assigned while preserving exact equal quotas. This produces the granular / pointillist interweaving from the original browser prototype.

### Organic Territories

Each layer receives its exact quota from the currently unassigned work surface, but selection is driven by smooth deterministic random fields. The Territory control moves from fine fragments toward broad islands/territories without changing the conservation rule.

### Vector Cutouts — mixed primitives

Vector Cutouts use hard geometry rather than seed growth. Every candidate cutout independently chooses a random complexity from `1` through **Max primitive points**:

- **1 point** → hard rotated stamp / block
- **2 points** → straight ribbon / slice
- **3+ points** → connected polygon

**Point spread** is the maximum separation range for the control geometry. At `100%`, a primitive may span the complete width and/or height of the canvas. Each primitive still randomizes its actual span anywhere from tiny/local up to that maximum, so successive cutouts do not share a fixed spacing or scale. **Cutout scale** biases the random draw toward compact or broad shapes without removing that full range of possibilities.

Every candidate is intersected with the still-unassigned work surface. If it would overshoot a source's remaining quota, PXCOMP clips it with a straight directional half-plane, keeping the boundary crisp. The final source receives the remainder, guaranteeing the core invariant.

PXCOMP retains the v0.2 (`algorithm_version: 1.1`) fixed-point polygon generator so previously saved vector projects remain reproducible. Editing an allocation control upgrades that project to the current `1.2` mixed-primitive algorithm.

See `docs/VECTOR-TERRITORIES.md` for the algorithm definition.

## Desktop workflow in v0.4

The v0.4 iteration keeps the image/allocation engine unchanged and reorganizes the interface around four direct steps:

1. **Sources** — add or drag/drop photographs and RAW files, select, navigate, remove, or drag to reorder the sequential source list.
2. **Canvas & crop** — set output dimensions, apply common aspect-ratio presets, swap orientation, drag the active image to crop, and use the mouse wheel to zoom.
3. **Composition** — choose Pixel Random, Organic Territories, or Vector Cutouts, adjust only the controls relevant to that mode, choose a deterministic seed, and generate the composite.
4. **Project & export** — open/save `.pxcomp` recipes and export through one compact format selector.

Additional usability changes:

- resizable sidebar/workspace splitter
- drag/drop images onto the source list, canvas, or application window
- drag source rows to reorder them
- previous/next source navigation
- live source-count and equal-share summary
- crop center/reset controls
- debounced crop redraw while dragging or zooming
- responsive fit-to-window canvas preview
- explicit **CROP**, **COMPOSITE**, and **UPDATE NEEDED** workspace states
- standard project Save / Save As behavior
- indeterminate progress/status feedback during render and export
- keyboard shortcuts: `Ctrl+I` add images, `Ctrl+O` open, `Ctrl+S` save, `Ctrl+Return` generate, `Ctrl+R` new seed, `PgUp/PgDown` navigate sources, `Ctrl+0` reset crop, `Delete` remove source

See `docs/UX-v0.4.md` for the interface refinement brief.

## Desktop features

- Windows desktop UI (PySide6)
- multi-file photographic / RAW input
- common canvas size
- per-photo crop, zoom and reposition
- deterministic seed
- Pixel Random, Organic Territories, and Vector Cutouts
- randomized vector complexity from 1 through a selected maximum
- full-canvas-capable point spread control
- non-destructive `.pxcomp` project recipes
- JPEG / PNG input
- WebP / AVIF where supported by the installed Pillow build
- TIFF input including high-bit-depth TIFF through `tifffile`
- multi-brand camera RAW decoding through `rawpy` / LibRaw (camera support follows the bundled LibRaw version)
- PNG and JPEG export
- 8-bit TIFF export
- **16-bit RGB TIFF master export**
- **layered Photoshop PSD export**, one transparent full-canvas layer per source

## Precision

RAW files are decoded directly through LibRaw. The 16-bit TIFF path asks the decoder for 16-bit RGB and keeps a 16-bit processing buffer through resize/composition/export. Ordinary 8-bit sources are promoted to 16-bit when included in a 16-bit TIFF export; promotion cannot create detail that did not exist in the original source.

PSD is currently exported as an 8-bit RGB layered document because the editable layer path is designed for broad Photoshop compatibility.

## Run from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,build]"
pxcomp
```

## Test

```powershell
python -m pytest
```

## Build the Windows executable

```powershell
pyinstaller --clean --noconfirm PXCOMP.spec
```

The executable is written to `dist/PXCOMP.exe`.

GitHub Actions runs the same tests and packaging process and publishes a Windows x64 workflow artifact.

## Current limits

- The desktop build prioritizes correctness and a usable photographic workflow over tiled/GPU rendering. Very large canvases can consume substantial RAM during full-resolution generation/export.
- RAW support is broad but depends on the LibRaw version bundled by `rawpy`; newly released or unusual cameras can require a newer decoder.
- 16-bit TIFF is the high-precision master path; PSD is 8-bit layered in v0.4.
- Source paths in `.pxcomp` projects currently point to the original local files rather than embedding copies.

## Development

Read `AGENTS.md` before changing the engine. The ownership invariant is the non-negotiable identity of PXCOMP.
