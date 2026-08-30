from pxcomp.model import Project, SourceSpec, load_project, save_project


def test_project_round_trip(tmp_path):
    project = Project(
        width=6000,
        height=4000,
        mode="organic",
        seed=99182,
        territory=73,
        sources=[SourceSpec("C:/shoot/001.CR3", zoom=1.25, offset_x=-120.0, offset_y=42.0)],
    )
    path = tmp_path / "work.pxcomp"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.to_dict() == project.to_dict()
