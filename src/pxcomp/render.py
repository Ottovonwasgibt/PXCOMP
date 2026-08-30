from __future__ import annotations

from dataclasses import replace
import numpy as np
from PIL import Image

from .imaging import load_image_array
from .model import Project, SourceSpec


def _resize_rgb(array: np.ndarray, width: int, height: int) -> np.ndarray:
    if width < 1 or height < 1:
        raise ValueError("Resize dimensions must be positive")
    if array.dtype == np.uint8:
        image = Image.fromarray(array, mode="RGB")
        return np.asarray(image.resize((width, height), Image.Resampling.LANCZOS)).copy()
    if array.dtype == np.uint16:
        channels: list[np.ndarray] = []
        for channel in range(3):
            # PIL mode I supports high-range integer interpolation.
            plane = Image.fromarray(array[..., channel].astype(np.int32))
            resized = np.asarray(
                plane.resize((width, height), Image.Resampling.BILINEAR), dtype=np.int32
            )
            channels.append(np.clip(resized, 0, 65535).astype(np.uint16))
        return np.stack(channels, axis=2)
    raise ValueError(f"Unsupported dtype for resize: {array.dtype}")


def _cover_geometry(
    source_width: int,
    source_height: int,
    canvas_width: int,
    canvas_height: int,
    zoom: float,
    offset_x: float,
    offset_y: float,
) -> tuple[int, int, int, int]:
    base_scale = max(canvas_width / source_width, canvas_height / source_height)
    scale = base_scale * max(1.0, float(zoom))
    scaled_width = max(canvas_width, int(round(source_width * scale)))
    scaled_height = max(canvas_height, int(round(source_height * scale)))

    max_offset_x = max(0.0, (scaled_width - canvas_width) / 2.0)
    max_offset_y = max(0.0, (scaled_height - canvas_height) / 2.0)
    offset_x = float(np.clip(offset_x, -max_offset_x, max_offset_x))
    offset_y = float(np.clip(offset_y, -max_offset_y, max_offset_y))

    left = int(round((scaled_width - canvas_width) / 2.0 - offset_x))
    top = int(round((scaled_height - canvas_height) / 2.0 - offset_y))
    left = int(np.clip(left, 0, max(0, scaled_width - canvas_width)))
    top = int(np.clip(top, 0, max(0, scaled_height - canvas_height)))
    return scaled_width, scaled_height, left, top


def render_source(
    source: SourceSpec,
    canvas_width: int,
    canvas_height: int,
    bit_depth: int = 8,
    preview: bool = False,
) -> np.ndarray:
    array = load_image_array(source.path, bit_depth=bit_depth, preview=preview)
    source_height, source_width = array.shape[:2]
    scaled_width, scaled_height, left, top = _cover_geometry(
        source_width,
        source_height,
        canvas_width,
        canvas_height,
        source.zoom,
        source.offset_x,
        source.offset_y,
    )
    if (scaled_width, scaled_height) != (source_width, source_height):
        array = _resize_rgb(array, scaled_width, scaled_height)
    return np.ascontiguousarray(array[top : top + canvas_height, left : left + canvas_width])


def render_composite(project: Project, owners: np.ndarray, bit_depth: int = 8) -> np.ndarray:
    project.validate()
    if owners.shape != (project.height, project.width):
        raise ValueError("Ownership map size does not match project canvas")
    if not project.sources:
        raise ValueError("Project has no source images")
    dtype = np.uint16 if bit_depth == 16 else np.uint8
    output = np.zeros((project.height, project.width, 3), dtype=dtype)
    for index, source in enumerate(project.sources):
        rendered = render_source(source, project.width, project.height, bit_depth=bit_depth)
        mask = owners == index
        output[mask] = rendered[mask]
    return output


def preview_dimensions(width: int, height: int, max_width: int = 1100, max_height: int = 760) -> tuple[int, int]:
    scale = min(max_width / width, max_height / height, 1.0)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def scaled_source(source: SourceSpec, scale_x: float, scale_y: float) -> SourceSpec:
    return replace(
        source,
        offset_x=source.offset_x * scale_x,
        offset_y=source.offset_y * scale_y,
    )


def downsample_owners(owners: np.ndarray, width: int, height: int) -> np.ndarray:
    src_height, src_width = owners.shape
    xs = np.minimum((np.arange(width, dtype=np.float64) * src_width / width).astype(np.int64), src_width - 1)
    ys = np.minimum((np.arange(height, dtype=np.float64) * src_height / height).astype(np.int64), src_height - 1)
    return owners[np.ix_(ys, xs)]


def render_preview_source(project: Project, index: int, max_width: int = 1100, max_height: int = 760) -> np.ndarray:
    width, height = preview_dimensions(project.width, project.height, max_width, max_height)
    source = scaled_source(project.sources[index], width / project.width, height / project.height)
    return render_source(source, width, height, bit_depth=8, preview=True)


def render_preview_composite(project: Project, owners: np.ndarray, max_width: int = 1100, max_height: int = 760) -> np.ndarray:
    width, height = preview_dimensions(project.width, project.height, max_width, max_height)
    small_owners = downsample_owners(owners, width, height)
    output = np.zeros((height, width, 3), dtype=np.uint8)
    scale_x = width / project.width
    scale_y = height / project.height
    for index, original_source in enumerate(project.sources):
        source = scaled_source(original_source, scale_x, scale_y)
        rendered = render_source(source, width, height, bit_depth=8, preview=True)
        mask = small_owners == index
        output[mask] = rendered[mask]
    return output
