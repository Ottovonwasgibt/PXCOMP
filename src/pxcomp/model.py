from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

ALGORITHM_VERSION = "1.0"


@dataclass
class SourceSpec:
    path: str
    name: str | None = None
    zoom: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    def __post_init__(self) -> None:
        if self.name is None:
            self.name = Path(self.path).name
        self.zoom = max(1.0, float(self.zoom))
        self.offset_x = float(self.offset_x)
        self.offset_y = float(self.offset_y)


@dataclass
class Project:
    width: int = 1200
    height: int = 1200
    mode: str = "pixel"
    seed: int = 12345
    territory: int = 55
    sources: list[SourceSpec] = field(default_factory=list)
    algorithm_version: str = ALGORITHM_VERSION

    def validate(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError("Canvas dimensions must be positive")
        if self.mode not in {"pixel", "organic"}:
            raise ValueError(f"Unsupported allocation mode: {self.mode}")
        if not 0 <= int(self.territory) <= 100:
            raise ValueError("Territory must be between 0 and 100")
        if len(self.sources) > 65534:
            raise ValueError("PXCOMP supports at most 65,534 sources per project")

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        sources = [SourceSpec(**entry) for entry in data.get("sources", [])]
        project = cls(
            width=int(data.get("width", 1200)),
            height=int(data.get("height", 1200)),
            mode=str(data.get("mode", "pixel")),
            seed=int(data.get("seed", 12345)),
            territory=int(data.get("territory", 55)),
            sources=sources,
            algorithm_version=str(data.get("algorithm_version", ALGORITHM_VERSION)),
        )
        project.validate()
        return project


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    path.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")


def load_project(path: str | Path) -> Project:
    path = Path(path)
    return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
