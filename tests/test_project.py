from pxcomp.model import Project, SourceSpec, load_project, save_project


def test_project_round_trip(tmp_path):
    project = Project(
        width=6000,
        height=4000,
        mode="vector",
        seed=99182,
        territory=73,
        vector_points=9,
        sources=[
            SourceSpec(
                "C:/shoot/001.CR3",
                zoom=1.25,
                offset_x=-120.0,
                offset_y=42.0,
            )
        ],
    )
    path = tmp_path / "work.pxcomp"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.to_dict() == project.to_dict()


def test_old_project_defaults_vector_points():
    loaded = Project.from_dict(
        {
            "width": 1200,
            "height": 1200,
            "mode": "organic",
            "seed": 12,
            "territory": 55,
            "sources": [],
            "algorithm_version": "1.0",
        }
    )
    assert loaded.vector_points == 7
