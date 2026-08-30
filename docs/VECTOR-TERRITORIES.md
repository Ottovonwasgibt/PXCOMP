# Vector Territories

PXCOMP v0.3 extends the hard-edged vector grammar into a mixed-primitive system. The objective is a cut-paper / stencil / collage geometry rather than radial seed growth.

## Core ownership rule

For each active layer, candidate vector primitives are rasterized only as ownership masks and intersected with the still-unassigned work surface. Claimed pixels are removed from the possibilities available to later layers. Each source receives its exact integer quota; the final source receives the remainder.

Therefore:

- every output pixel has exactly one owner;
- source shares differ by at most one pixel;
- source masks never overlap;
- there are no holes.

## Primitive complexity

`Max primitive points` is an upper bound, not a fixed point count. Every new candidate independently samples an integer from `1..max`.

- **1** — one random anchor generates a hard rotated stamp/block.
- **2** — two control points generate a straight hard-edged ribbon/slice.
- **3 or more** — the sampled points are ordered into a closed polygon.

For example, selecting `12` does **not** create twelve-point shapes repeatedly. Every candidate may independently use 1, 2, 3, ... or 12 control points.

## Point distance / spread

`Point spread` caps how far a primitive's control geometry can extend relative to the canvas dimensions. At `100%`, the sampled geometry can span the complete width and/or height of the image.

Within that cap, the actual span is randomized independently for every candidate from near-pixel scale to the configured maximum. `Cutout scale` changes the probability bias toward smaller or larger spans; it does not force the vectors into one repeated spacing.

This separates three ideas:

- **Max primitive points** controls possible structural complexity.
- **Point spread** controls the maximum spatial reach.
- **Cutout scale** biases whether the randomly available range tends compact or broad.

## Sequential reduction

For layer `i`:

1. compute the exact remaining quota for the layer;
2. choose a random primitive complexity from `1..Max primitive points`;
3. choose independently randomized horizontal and vertical spans within `Point spread`;
4. create the corresponding stamp, ribbon, or polygon;
5. rasterize the primitive with a hard edge;
6. intersect it with pixels still unassigned by earlier layers;
7. claim the full intersection if it fits the quota;
8. if it overshoots, clip it with a random straight vector half-plane to take exactly the required count;
9. continue with another primitive until the layer quota is full;
10. remove those pixels from the work surface and continue to the next source.

The process is deterministic for an identical algorithm version, seed, parameters, dimensions, layer order, and crop transforms.

## Legacy reproducibility

PXCOMP v0.2 used `algorithm_version: 1.1`, where every Vector Cutout used one fixed polygon point count and comparatively similar spatial spans. v0.3 keeps that generator internally so saved v0.2 projects reproduce their original masks.

New projects use `algorithm_version: 1.2`. Changing an allocation control on a loaded v0.2 vector project upgrades it to the current mixed-primitive generator.
