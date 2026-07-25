from pathlib import Path

import store


def test_render_then_parse_preserves_every_field():
    original = store.Task(
        id=42,
        title="Replay audio desync after ~2 minutes",
        type="BUG",
        bucket="now",
        status="open",
        order=1,
        created="2026-07-25",
        started=None,
        done=None,
        body="Audio drifts out of sync.\n\nProbably the pts rebase.",
    )

    reparsed = store.parse_task(store.render_task(original))

    assert reparsed.id == 42
    assert reparsed.title == "Replay audio desync after ~2 minutes"
    assert reparsed.type == "BUG"
    assert reparsed.bucket == "now"
    assert reparsed.status == "open"
    assert reparsed.order == 1
    assert reparsed.created == "2026-07-25"
    assert reparsed.started is None
    assert reparsed.done is None


def test_body_survives_verbatim_including_yaml_lookalikes():
    tricky = 'key: value\n---\n"quoted" and `backticks`\n\n  indented\ttab'
    task = store.Task(
        id=1, title="t", type="BUG", bucket="now", status="open", order=0,
        created="2026-07-25", started=None, done=None, body=tricky,
    )

    assert store.parse_task(store.render_task(task)).body == tricky


def test_task_slug_is_filename_safe_and_bounded():
    assert store.task_slug("Replay audio desync after ~2 minutes!") == "replay-audio-desync-after-2-minutes"
    assert len(store.task_slug("x" * 200)) <= 50
