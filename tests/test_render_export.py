from pathlib import Path
import numpy as np
from PIL import Image
import tifffile
from psd_tools import PSDImage

from pxcomp.alloc import generate_ownership
from pxcomp.exports import export_psd, export_tiff
from pxcomp.model import Project, SourceSpec
from pxcomp.render import render_composite


def _make_source(path: Path, color: tuple[int, int, int]) -> None:
    data = np.zeros((20, 30, 3), dtype=np.uint8)
    data[:] = color
    Image.fromarray(data, mode="RGB").save(path)


def test_composite_contains_exact_source_regions(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _make_source(a, (255, 0, 0))
    _make_source(b, (0, 255, 0))
    project = Project(width=24, height=18, sources=[SourceSpec(str(a)), SourceSpec(str(b))])
    owners = generate_ownership(project.width, project.height, 2, 42, "pixel")
    composite = render_composite(project, owners, 8)
    assert np.all(composite[owners == 0] == np.array([255, 0, 0], dtype=np.uint8))
    assert np.all(composite[owners == 1] == np.array([0, 255, 0], dtype=np.uint8))


def test_tiff_16bit_export(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _make_source(a, (128, 64, 32))
    _make_source(b, (32, 64, 128))
    project = Project(width=16, height=12, sources=[SourceSpec(str(a)), SourceSpec(str(b))])
    owners = generate_ownership(16, 12, 2, 9, "organic", 60)
    output = tmp_path / "out.tif"
    export_tiff(project, owners, output, bit_depth=16)
    image = tifffile.imread(output)
    assert image.dtype == np.uint16
    assert image.shape == (12, 16, 3)


def test_layered_psd_export(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _make_source(a, (255, 0, 0))
    _make_source(b, (0, 0, 255))
    project = Project(width=12, height=10, sources=[SourceSpec(str(a)), SourceSpec(str(b))])
    owners = generate_ownership(12, 10, 2, 5, "pixel")
    output = tmp_path / "out.psd"
    export_psd(project, owners, output)
    psd = PSDImage.open(output)
    assert psd.size == (12, 10)
    assert len(psd) == 2
