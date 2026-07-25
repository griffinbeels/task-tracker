import pytest

import inbox
import registry


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def test_save_note_stores_text_verbatim():
    tricky = 'line one\n---\n"quoted"\n\n  indented'

    note = inbox.save_note(tricky)

    assert inbox.list_notes()[0].text == tricky
    assert note.id


def test_save_note_never_overwrites_an_existing_note():
    first = inbox.save_note("one")
    second = inbox.save_note("two")

    assert first.id != second.id
    assert sorted(n.text for n in inbox.list_notes()) == ["one", "two"]


def test_list_notes_is_oldest_first():
    inbox.save_note("one")
    inbox.save_note("two")

    assert [n.text for n in inbox.list_notes()] == ["one", "two"]


def test_file_note_creates_the_task_and_clears_the_note(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    note = inbox.save_note("Audio drifts out of sync after ~2 minutes")

    task = inbox.file_note(note.id, repo, "Replay audio desync", "BUG", "now")

    assert task.body == "Audio drifts out of sync after ~2 minutes"
    assert task.title == "Replay audio desync"
    assert task.bucket == "now"
    assert inbox.list_notes() == []


def test_file_note_rejects_an_unknown_note(tmp_path):
    with pytest.raises(FileNotFoundError):
        inbox.file_note("nope", tmp_path, "t", "BUG", "now")


def test_notes_are_written_with_lf_endings():
    note = inbox.save_note("line one\nline two")

    assert b"\r" not in (inbox.inbox_dir() / f"{note.id}.md").read_bytes()
