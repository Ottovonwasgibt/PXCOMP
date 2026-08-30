# PXCOMP v0.4 interface refinement

This iteration keeps the image/allocation engine unchanged and refines the desktop workflow around four steps: Sources, Canvas & Crop, Composition, and Project & Export.

## Goals

- reduce stacked controls and repeated dialogs
- make the app usable by drag/drop without reading instructions first
- make sequential source order visible and easy to change
- keep crop interaction directly on the image surface
- keep composition controls mode-specific
- make project save/open and export behavior predictable
- expose useful keyboard shortcuts without making them mandatory

## Changes

- resizable sidebar/workspace splitter
- drag/drop images or `.pxcomp` projects onto the app
- drag source rows to reorder, plus move up/down buttons
- previous/next source navigation
- source count and exact target share summary
- canvas aspect-ratio presets and width/height swap
- mouse-wheel crop zoom, drag-to-position, center and reset actions
- debounced crop redraw during slider/drag input
- clearer Crop / Composite / Update Needed workspace state
- compact export-format selector with one Export action
- normal Save behavior after a project has a path, plus Save As
- standard shortcuts: Ctrl+I add images, Ctrl+O open, Ctrl+S save, Ctrl+Return generate, Ctrl+R new seed, PgUp/PgDown sources, Ctrl+0 reset crop, Delete remove source
- indeterminate progress/status feedback for render/export operations

The ownership invariant and allocation algorithms remain unchanged in this iteration.
