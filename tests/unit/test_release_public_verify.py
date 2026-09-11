"""Public re-resolution must retain the approved release digest."""

import copy
import io
import json
import tarfile

import pytest

from script import release_public_verify as public
from script import release_support as support


@pytest.fixture
def resolution(monkeypatch):
    url = "https://files.pythonhosted.org/packages/godot_ai-4.1.0-py3-none-any.whl"
    metadata = {
        "urls": [
            {
                "filename": "godot_ai-4.1.0-py3-none-any.whl",
                "url": url,
                "size": 123,
                "digests": {"sha256": "a" * 64},
            }
        ]
    }
    report = {
        "install": [
            {
                "metadata": {"name": "godot-ai", "version": "4.1.0"},
                "download_info": {"url": url, "archive_info": {"hashes": {"sha256": "a" * 64}}},
            }
        ]
    }
    record = {
        "version": "4.1.0",
        "files": {"dist/godot_ai-4.1.0-py3-none-any.whl": {"size": 123, "sha256": "a" * 64}},
    }
    reads = []
    monkeypatch.setattr(public.promotion, "public_json", lambda url: metadata)
    monkeypatch.setattr(public.promotion, "verify_public_file", lambda *args: reads.append(args))
    return report, record, metadata, reads


def test_public_resolution_redownloads_approved_bytes(resolution):
    report, record, _, reads = resolution
    result = public.verify_resolution(report, record)
    assert result[0]["sha256"] == "a" * 64 and result[0]["size"] == 123
    assert reads == [
        (result[0]["url"], {"size": 123, "sha256": "a" * 64}, {"files.pythonhosted.org"})
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "installed_hash",
        "approved_hash",
        "version",
        "yanked",
        "foreign_host",
        "missing_release",
        "duplicate",
    ],
)
def test_public_resolution_rejects_unapproved_or_incomplete_install(resolution, fault):
    report, record, metadata, _ = resolution
    item = report["install"][0]
    if fault == "installed_hash":
        item["download_info"]["archive_info"]["hashes"]["sha256"] = "b" * 64
    elif fault == "approved_hash":
        next(iter(record["files"].values()))["sha256"] = "b" * 64
    elif fault == "version":
        item["metadata"]["version"] = "4.1.1"
    elif fault == "yanked":
        metadata["urls"][0]["yanked"] = True
    elif fault == "foreign_host":
        item["download_info"]["url"] = "https://example.com/package.whl"
    elif fault == "missing_release":
        report["install"] = []
    else:
        report["install"].append(copy.deepcopy(item))
    with pytest.raises(support.ReleaseError):
        public.verify_resolution(report, record)


def test_reads_indented_pip_report_and_still_rejects_duplicate_keys(tmp_path):
    report = tmp_path / "pip.json"
    report.write_text(json.dumps({"version": "1", "install": []}, indent=2))
    assert public.read_resolution(report) == {"version": "1", "install": []}
    report.write_text('{"install": [], "install": [1]}')
    with pytest.raises(support.ReleaseError):
        public.read_resolution(report)


def test_build_requirements_come_from_qualified_source_archive(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    content = b'[build-system]\nrequires = ["setuptools==84.0.0"]\n'
    with tarfile.open(dist / "godot_ai-4.1.0.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("godot_ai-4.1.0/pyproject.toml")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    assert public.build_requirements(tmp_path, "4.1.0") == ["setuptools==84.0.0"]


def test_build_resolution_does_not_require_release_package(resolution):
    report, record, _, reads = resolution
    report["install"][0]["metadata"] = {"name": "setuptools", "version": "84.0.0"}
    result = public.verify_resolution(report, record, require_release=False)
    assert result[0]["name"] == "setuptools" and len(reads) == 1
