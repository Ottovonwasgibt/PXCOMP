from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image
from psd_tools import PSDImage
import tifffile

from .model import Project
from .render import render_composite, render_source


def export_png(project: Project, owners: np.ndarray, path: str | Path) -> None:
    array = render_composite(project, owners, bit_depth=8)
    Image.fromarray(array, mode="RGB").save(path, format="PNG", optimize=True)


def export_jpeg(project: Project, owners: np.ndarray, path: str | Path, quality: int = 95) -> None:
    array = render_composite(project, owners, bit_depth=8)
    Image.fromarray(array, mode="RGB").save(path, format="JPEG", quality=quality, subsampling=0)


def export_tiff(project: Project, owners: np.ndarray, path: str | Path, bit_depth: int = 16) -> None:
    if bit_depth not in {8, 16}:
        raise ValueError("TIFF bit depth must be 8 or 16")
    array = render_composite(project, owners, bit_depth=bit_depth)
    tifffile.imwrite(
        path,
        array,
        photometric="rgb",
        compression="deflate",
        metadata={
            "Software": "PXCOMP",
            "PXCOMPSeed": int(project.seed),
            "PXCOMPMode": project.mode,
            "PXCOMPAlgorithm": project.algorithm_version,
        },
    )


def export_psd(project: Project, owners: np.ndarray, path: str | Path) -> None:
    if project.width > 30000 or project.height > 30000:
        raise ValueError("PSD export is limited to 30,000 pixels per dimension; reduce canvas size")
    if owners.shape != (project.height, project.width):
        raise ValueError("Ownership map size does not match project canvas")

    psd = PSDImage.new(mode="RGB", size=(project.width, project.height), depth=8)
    total = owners.size
    for index, source in enumerate(project.sources):
        rgb = render_source(source, project.width, project.height, bit_depth=8)
        alpha = np.where(owners == index, 255, 0).astype(np.uint8)
        rgba = np.dstack((rgb, alpha))
        share = int(np.count_nonzero(owners == index)) * 100.0 / total
        name = f"{index + 1:02d} — {source.name} — {share:.4f}%"
        psd.create_pixel_layer(Image.fromarray(rgba, mode="RGBA"), name=name, top=0, left=0)
    psd.save(path)
