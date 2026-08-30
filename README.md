# PXCOMP

PXCOMP is a Windows desktop image compositor for combining a sequence of photographs through mutually exclusive spatial ownership.

## Core rule

For `N` source photographs, every output coordinate belongs to exactly one source. The integer pixel quotas are equal to within one pixel when the canvas pixel count is not divisible by `N`.

That guarantees:

- **100% canvas coverage**
- **0% overlap between source masks**
- **0 unassigned pixels**
- deterministic reconstruction from the project seed and algorithm parameters

## Allocation modes

### Pixel Random

Every coordinate is randomly assigned while preserving exact equal quotas. This produces the granular / pointillist interweaving from the original browser prototype.

### Organic Territories

Each layer receives its exact quota from the currently unassigned work surface, but selection is driven by smooth deterministic random fields. The Territory control moves from fine fragments toward broad islands/territories without changing the conservation rule.

### Vector Cutouts

PXCOMP v0.2 adds hard-edged vector-derived territories. Random points are connected into closed polygon shapes, clipped against the remaining unassigned work surface, and accumulated until each source reaches its exact quota. When a candidate polygon overshoots the remaining quota, it is clipped by a straight directional vector cut rather than feathered or randomly eroded.

Controls include **Cutout scale** and **Vector points per cutout**. This mode is intended to produce collage / stencil / cut-paper geometry instead of radial seed-growth blobs. See `docs/VECTOR-TERRITORIES.md` for the algorithm definition.

## Desktop features in v0.2

- Windows desktop UI (PySide6)
- drag/drop-style multi-file selection
- common canvas size
- per-photo crop, zoom and reposition
- deterministic seed
- Pixel Random, Organic Territories, and Vector Cutouts
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

GitHub Actions runs the same tests and packaging process and publishes `PXCOMP-windows-x64` as a workflow artifact.

## Current limits

- The desktop build prioritizes correctness and a usable photographic workflow over tiled/GPU rendering. Very large canvases can consume substantial RAM during full-resolution generation/export.
- RAW support is broad but depends on the LibRaw version bundled by `rawpy`; newly released or unusual cameras can require a newer decoder.
- 16-bit TIFF is the high-precision master path; PSD is 8-bit layered in v0.2.
- Source paths in `.pxcomp` projects currently point to the original local files rather than embedding copies.

## Development

Read `AGENTS.md` before changing the engine. The ownership invariant is the non-negotiable identity of PXCOMP.
