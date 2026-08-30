# Vector Territories

PXCOMP v0.2 adds a hard-edged allocation grammar alongside Pixel Random and Organic Territories.

## Rule

For each active layer, PXCOMP samples a configurable number of points, connects them into a closed polygon, rasterizes that polygon only as an ownership candidate, and intersects it with the still-unassigned work surface. If the candidate would exceed the layer's exact integer quota, the candidate is clipped by a random straight vector half-plane so the layer receives exactly its remaining pixel count. The final layer receives the remainder.

This preserves the PXCOMP invariant: every output pixel has exactly one owner, source shares differ by at most one pixel, there are no overlaps, and there are no holes.

## Artistic distinction

Organic Territories are derived from smooth random fields and therefore tend toward soft islands and dust-like boundaries. Vector Cutouts are not radial seed growth. Their shape grammar is polygonal, directional, and hard-edged, producing a collage / stencil / cut-paper feeling.

## Controls

- `Cutout scale` controls the typical span of candidate polygons across the canvas.
- `Vector points per cutout` controls polygon complexity from triangular shards toward more articulated contours.
- `Random seed` makes the geometry reproducible.
