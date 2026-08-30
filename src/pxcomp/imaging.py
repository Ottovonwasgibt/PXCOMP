from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
import rawpy
import tifffile

RAW_EXTENSIONS = {
    ".3fr", ".ari", ".arw", ".bay", ".cap", ".cr2", ".cr3", ".crw",
    ".dcr", ".dcs", ".dng", ".drf", ".eip", ".erf", ".fff", ".gpr",
    ".iiq", ".k25", ".kdc", ".mdc", ".mef", ".mos", ".mrw", ".nef",
    ".nrw", ".orf", ".pef", ".ptx", ".pxn", ".raf", ".raw", ".rwl",
    ".rw2", ".rwz", ".sr2", ".srf", ".srw", ".x3f",
}

RASTER_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".tif", ".tiff"
}

SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | RASTER_EXTENSIONS


def is_raw(path: str | Path) -> bool:
    return Path(path).suffix.lower() in RAW_EXTENSIONS


def _ensure_rgb(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array)
    if array.ndim > 3:
        array = array[0]
    if array.ndim == 2:
        array = np.repeat(array[..., None], 3, axis=2)
    if array.ndim != 3:
        raise ValueError(f"Unsupported image shape: {array.shape}")
    if array.shape[-1] == 1:
        array = np.repeat(array, 3, axis=2)
    elif array.shape[-1] >= 3:
        array = array[..., :3]
    else:
        raise ValueError(f"Unsupported channel count: {array.shape[-1]}")
    return np.ascontiguousarray(array)


def _convert_depth(array: np.ndarray, bit_depth: int) -> np.ndarray:
    array = _ensure_rgb(array)
    if bit_depth == 8:
        if array.dtype == np.uint8:
            return array
        if np.issubdtype(array.dtype, np.integer):
            maximum = np.iinfo(array.dtype).max
            return np.clip(np.rint(array.astype(np.float64) * (255.0 / maximum)), 0, 255).astype(np.uint8)
        data = np.nan_to_num(array.astype(np.float64))
        maximum = float(data.max()) if data.size else 1.0
        if maximum <= 1.0:
            data *= 255.0
        return np.clip(np.rint(data), 0, 255).astype(np.uint8)

    if bit_depth == 16:
        if array.dtype == np.uint16:
            return array
        if array.dtype == np.uint8:
            return (array.astype(np.uint16) * np.uint16(257)).astype(np.uint16)
        if np.issubdtype(array.dtype, np.integer):
            maximum = np.iinfo(array.dtype).max
            return np.clip(np.rint(array.astype(np.float64) * (65535.0 / maximum)), 0, 65535).astype(np.uint16)
        data = np.nan_to_num(array.astype(np.float64))
        maximum = float(data.max()) if data.size else 1.0
        if maximum <= 1.0:
            data *= 65535.0
        return np.clip(np.rint(data), 0, 65535).astype(np.uint16)

    raise ValueError("bit_depth must be 8 or 16")


def load_image_array(path: str | Path, bit_depth: int = 8, preview: bool = False) -> np.ndarray:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in RAW_EXTENSIONS:
        with rawpy.imread(str(path)) as raw:
            result = raw.postprocess(
                use_camera_wb=True,
                output_bps=16 if bit_depth == 16 else 8,
                half_size=bool(preview),
                no_auto_bright=False,
            )
        return _convert_depth(result, bit_depth)

    if suffix in {".tif", ".tiff"}:
        result = tifffile.imread(str(path))
        return _convert_depth(result, bit_depth)

    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        result = np.asarray(image)
    return _convert_depth(result, bit_depth)


def supported_file_filter() -> str:
    common = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
    return f"Supported images ({common});;All files (*.*)"
