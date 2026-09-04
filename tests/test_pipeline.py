import pipeline


def _write_pipeline(project, task_id, slug, frontmatter, retrospective=False):
    feature_dir = project / ".tasks" / "features" / f"{task_id:04d}-{slug}"
    feature_dir.mkdir(parents=True)
    (feature_dir / "pipeline.md").write_text(frontmatter, encoding="utf-8", newline="\n")
    if retrospective:
        (feature_dir / "retrospective.html").write_text("<html></html>", encoding="utf-8")
    return feature_dir


def test_lookup_returns_none_when_no_feature_folder_exists(tmp_path):
    project = tmp_path / "some-project"
    project.mkdir()

    assert pipeline.lookup(project, 124) is None


def test_lookup_joins_the_zero_padded_task_id_to_its_slugged_folder(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 124, "product-design-pipeline", """---
task: 124
title: Product design pipeline
stage: build
lane: prototype
pipeline: 1
updated: 2026-09-04
---
## Transitions
- 2026-09-04 created at spec (him)
""")

    result = pipeline.lookup(project, 124)

    assert result == {"stage": "build", "lane": "prototype"}


def test_lookup_reports_a_retrospective_only_when_the_file_exists(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 7, "small-fix", """---
task: 7
stage: done
lane: prototype
---
""", retrospective=True)

    result = pipeline.lookup(project, 7)

    assert result["stage"] == "done"
    assert result["retrospective"].endswith("retrospective.html")


def test_lookup_omits_retrospective_key_when_the_file_is_absent(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 7, "small-fix", """---
task: 7
stage: build
lane: prototype
---
""")

    result = pipeline.lookup(project, 7)

    assert "retrospective" not in result


def test_lookup_returns_none_for_a_pipeline_file_with_no_stage(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 3, "no-stage", """---
task: 3
lane: prototype
---
""")

    assert pipeline.lookup(project, 3) is None


def test_lookup_returns_none_rather_than_raising_on_malformed_yaml(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 3, "broken", """---
stage: [unterminated
---
""")

    assert pipeline.lookup(project, 3) is None


def test_lookup_returns_none_when_the_feature_folder_has_no_pipeline_file(tmp_path):
    project = tmp_path / "some-project"
    (project / ".tasks" / "features" / "0009-empty-folder").mkdir(parents=True)

    assert pipeline.lookup(project, 9) is None


def test_lookup_does_not_match_a_different_tasks_id_with_a_shared_prefix(tmp_path):
    project = tmp_path / "some-project"
    _write_pipeline(project, 12, "one", """---
stage: build
---
""")
    # 124 zero-pads to "0124", which is not a prefix match for "0012" or vice
    # versa -- guard against a naive string-prefix glob ever being reintroduced.
    assert pipeline.lookup(project, 124) is None
    assert pipeline.lookup(project, 12)["stage"] == "build"
