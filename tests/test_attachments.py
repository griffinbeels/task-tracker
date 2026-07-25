import base64

import pytest

import store

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake pixels"
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def test_an_attachment_lands_under_the_project_and_holds_the_real_bytes(tmp_path):
    path = store.save_attachment(tmp_path, PNG_DATA_URL)

    assert path.parent == tmp_path / ".tasks" / "attachments"
    assert path.suffix == ".png"
    assert path.read_bytes() == PNG_BYTES


def test_two_attachments_in_the_same_second_get_distinct_names(tmp_path):
    first = store.save_attachment(tmp_path, PNG_DATA_URL)
    second = store.save_attachment(tmp_path, PNG_DATA_URL)

    assert first != second
    assert first.read_bytes() == second.read_bytes() == PNG_BYTES


def test_the_attachments_directory_is_created_on_demand(tmp_path):
    # A project registered before this feature existed has no attachments/.
    assert not (tmp_path / ".tasks" / "attachments").exists()

    store.save_attachment(tmp_path, PNG_DATA_URL)

    assert (tmp_path / ".tasks" / "attachments").is_dir()


def test_a_jpeg_keeps_its_own_extension(tmp_path):
    url = "data:image/jpeg;base64," + base64.b64encode(b"jpeg bytes").decode()

    assert store.save_attachment(tmp_path, url).suffix == ".jpg"


@pytest.mark.parametrize("bad", [
    "not a data url at all",
    "data:image/png,notbase64encoded",        # missing the ;base64 marker
    "data:text/plain;base64,aGVsbG8=",        # not an image
    "data:image/png;base64,!!!not base64!!!",
])
def test_a_malformed_data_url_raises_rather_than_writing_a_file(tmp_path, bad):
    with pytest.raises(ValueError):
        store.save_attachment(tmp_path, bad)

    attachments = tmp_path / ".tasks" / "attachments"
    assert not attachments.exists() or not list(attachments.iterdir())
