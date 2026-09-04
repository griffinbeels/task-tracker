import pytest

import knowledge


@pytest.fixture(autouse=True)
def isolated_knowledge_root(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    root.mkdir()
    monkeypatch.setattr(knowledge, "knowledge_root", lambda: root)
    return root


def test_read_page_returns_the_files_text(isolated_knowledge_root):
    (isolated_knowledge_root / "index.md").write_text(
        "# Index\n\nsome text", encoding="utf-8")

    assert knowledge.read_page("index.md") == "# Index\n\nsome text"


def test_read_page_reaches_a_nested_page(isolated_knowledge_root):
    nested = isolated_knowledge_root / "wiki" / "process"
    nested.mkdir(parents=True)
    (nested / "some-lesson.md").write_text("body", encoding="utf-8")

    assert knowledge.read_page("wiki/process/some-lesson.md") == "body"


def test_read_page_refuses_a_relative_path_that_climbs_out_of_the_root(
        isolated_knowledge_root):
    outside = isolated_knowledge_root.parent / "secret.md"
    outside.write_text("do not read me", encoding="utf-8")

    with pytest.raises(ValueError):
        knowledge.read_page("../secret.md")


def test_read_page_refuses_an_absolute_path_outside_the_root(isolated_knowledge_root):
    outside = isolated_knowledge_root.parent / "secret.md"
    outside.write_text("do not read me", encoding="utf-8")

    with pytest.raises(ValueError):
        knowledge.read_page(str(outside))


def test_read_page_refuses_a_non_markdown_file(isolated_knowledge_root):
    (isolated_knowledge_root / "notes.txt").write_text("text", encoding="utf-8")

    with pytest.raises(ValueError):
        knowledge.read_page("notes.txt")


def test_read_page_refuses_a_page_that_does_not_exist(isolated_knowledge_root):
    with pytest.raises(ValueError):
        knowledge.read_page("missing.md")
