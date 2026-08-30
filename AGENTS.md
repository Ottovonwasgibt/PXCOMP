# PXCOMP agent instructions

PXCOMP is an experimental image compositor. Preserve the core invariant before adding features:

1. For a project with N sources, every output pixel has exactly one owner.
2. The union of source masks covers the full canvas.
3. Source masks never overlap.
4. Equal allocation uses deterministic integer quotas: shares may differ by at most one pixel when the canvas pixel count is not divisible by N.
5. A project recipe must remain reproducible from algorithm version + seed + mode + parameters + source transforms.

## Build discipline

- Primary development branch: `build/v0-desktop` until the first release is accepted.
- Python 3.12 is the reference runtime.
- Run `python -m pytest` before packaging.
- Windows package: `pyinstaller --clean --noconfirm PXCOMP.spec`.
- Do not silently reduce RAW/TIFF source precision for 16-bit TIFF export. JPEG/PNG/PSD export may use the 8-bit render path.
- PSD export must contain one full-canvas transparent pixel layer per source.
- Keep image processing code independent from the Qt UI so the allocation/render engine remains testable.
