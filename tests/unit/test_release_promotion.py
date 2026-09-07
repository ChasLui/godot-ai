"""Publication resume paths that the first v4.0.0 release exercised for real."""

from __future__ import annotations

import pytest

from script import release_promotion as promotion
from script import release_support as support

BASE = f"repos/{support.REPOSITORY}"


def test_release_for_tag_finds_the_draft_the_tag_endpoint_hides(monkeypatch):
    draft = {"tag_name": "v4.0.0", "draft": True, "id": 1}

    def fake_gh(*args, allow_missing=False):
        if args[0].startswith(f"{BASE}/releases/tags/"):
            assert allow_missing
            return None
        if args[0] == f"{BASE}/releases?per_page=100":
            return [{"tag_name": "v3.2.5", "draft": False}, draft]
        raise AssertionError(args)

    monkeypatch.setattr(promotion, "gh", fake_gh)
    assert promotion._release_for_tag(BASE, "v4.0.0") == draft
    assert promotion._release_for_tag(BASE, "v4.0.1") is None

    published = {"tag_name": "v4.0.0", "draft": False}
    monkeypatch.setattr(promotion, "gh", lambda *a, allow_missing=False: published)
    assert promotion._release_for_tag(BASE, "v4.0.0") is published


def test_verify_pypi_waits_for_the_index_to_list_a_fresh_upload(monkeypatch):
    record = {"version": "4.0.0", "files": {}}
    answers = iter([None, None, {"urls": []}])
    monkeypatch.setattr(promotion, "public_json", lambda url, allow_missing=False: next(answers))
    monkeypatch.setattr(promotion.time, "sleep", lambda seconds: None)
    with pytest.raises(support.ReleaseError, match="incomplete or unexpected"):
        promotion.verify_pypi(record)  # listed on the third try, then the inventory check runs

    monkeypatch.setattr(promotion, "public_json", lambda url, allow_missing=False: None)
    monkeypatch.setattr(promotion, "PYPI_INDEX_WAIT_SECONDS", 0.0)
    with pytest.raises(support.ReleaseError, match="still does not list 4.0.0"):
        promotion.verify_pypi(record)
