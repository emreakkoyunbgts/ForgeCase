"""CF-123: the OpenAPI exporter can update a subset and can prove a snapshot is current."""

import importlib
import json

import pytest

from scripts import export_openapi
from scripts.run_mesh import APPS

SELECTED = ["generator", "verifier"]


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """A private copy of the real snapshots, so a test never edits the repository."""
    target = tmp_path / "openapi"
    target.mkdir()
    for name in APPS:
        (target / f"{name}.json").write_text(
            export_openapi.snapshot(name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setattr(export_openapi, "OUTPUT", target)
    return target


def test_the_versioned_snapshots_are_current():
    assert export_openapi.check(SELECTED) == []


def test_check_reports_drift_and_fails(staged, capsys):
    stored = json.loads((staged / "generator.json").read_text(encoding="utf-8"))
    stored["info"]["version"] = "9.9.9"
    (staged / "generator.json").write_text(json.dumps(stored), encoding="utf-8")

    assert export_openapi.main(["--services", *SELECTED, "--check"]) == 1

    error = capsys.readouterr().err
    assert "generator: snapshot does not match the live contract" in error
    assert "verifier:" not in error


def test_check_reports_a_missing_snapshot_and_creates_nothing(tmp_path, monkeypatch, capsys):
    absent = tmp_path / "never-created"
    monkeypatch.setattr(export_openapi, "OUTPUT", absent)

    assert export_openapi.main(["--services", *SELECTED, "--check"]) == 1

    assert "is missing" in capsys.readouterr().err
    assert not absent.exists(), "--check must not create the output directory"


def test_check_leaves_every_file_untouched(staged):
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
              for path in sorted(staged.iterdir())}

    assert export_openapi.main(["--services", *SELECTED, "--check"]) == 0

    after = {path: (path.read_bytes(), path.stat().st_mtime_ns)
             for path in sorted(staged.iterdir())}
    assert after == before


def test_reformatting_alone_is_not_drift(staged):
    stored = json.loads((staged / "verifier.json").read_text(encoding="utf-8"))
    (staged / "verifier.json").write_text(
        json.dumps(stored, ensure_ascii=False, indent=8), encoding="utf-8"
    )

    assert export_openapi.check(["verifier"]) == []


def test_an_unknown_service_is_a_clear_cli_error(capsys):
    with pytest.raises(SystemExit) as exit_info:
        export_openapi.main(["--services", "generator", "nosuch"])

    assert exit_info.value.code == 2
    error = capsys.readouterr().err
    assert "unknown service(s): nosuch" in error
    for name in APPS:
        assert name in error, "the error must list the valid names"


def test_selecting_two_services_imports_and_writes_only_those(staged, monkeypatch):
    imported = []
    real = importlib.import_module

    def record(name):
        imported.append(name)
        return real(name)

    monkeypatch.setattr(export_openapi.importlib, "import_module", record)
    untouched = {name: (staged / f"{name}.json").read_bytes()
                 for name in APPS if name not in SELECTED}

    assert export_openapi.main(["--services", *SELECTED]) == 0

    assert imported == ["generator.GeneratorController", "verifier.VerifierController"]
    for name, content in untouched.items():
        assert (staged / f"{name}.json").read_bytes() == content


def test_exporting_twice_produces_the_same_bytes(staged):
    export_openapi.main(["--services", *SELECTED])
    first = {name: (staged / f"{name}.json").read_bytes() for name in SELECTED}

    export_openapi.main(["--services", *SELECTED])

    assert {name: (staged / f"{name}.json").read_bytes() for name in SELECTED} == first


def test_the_default_selection_is_still_every_service(staged, monkeypatch):
    exported = []
    monkeypatch.setattr(export_openapi, "export", exported.extend)

    assert export_openapi.main([]) == 0

    assert exported == list(APPS)


def test_the_written_form_stays_utf8_indented_with_a_final_newline(staged):
    export_openapi.main(["--services", "generator"])
    path = staged / "generator.json"

    # Read back through universal newlines: Windows stores CRLF, git normalises it.
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert text == export_openapi.serialize(json.loads(text))
    assert "\n  " in text, "indent=2 is part of the reviewable form"
    # ensure_ascii=False keeps non-Latin prose readable instead of \\u escapes.
    assert "azaltıldı" in path.read_bytes().decode("utf-8")


def test_a_corrupt_snapshot_is_reported_rather_than_raised(staged, capsys):
    (staged / "generator.json").write_text("{not json", encoding="utf-8")

    assert export_openapi.main(["--services", "generator", "--check"]) == 1

    assert "snapshot is not valid JSON" in capsys.readouterr().err
