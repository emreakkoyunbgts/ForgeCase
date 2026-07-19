"""Tests for the Publisher."""
import json

from common.contract import load_seed
from publisher.publisher import print_case_study, render_docx


def test_print_case_study_outputs_valid_json(capsys):
    case_study = {"title": "A grounded case study"}

    print_case_study(case_study)

    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed["title"] == case_study["title"]


def test_renders_without_crashing(tmp_path):
    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        case_study = json.load(f)

    out = tmp_path / "eng-01.docx"
    render_docx(case_study, "caseforge-testdata/templates/case_study_template.docx", out)


def test_real_client_name_never_leaks(tmp_path):
    """eng-01 may NOT be named. Check the real name is nowhere in the output."""
    with open("caseforge-testdata/case_studies/eng-01_clean.json") as f:
        case_study = json.load(f)

    record = load_seed("eng-01")
    out = tmp_path / "eng-01.docx"
    written = render_docx(case_study, "caseforge-testdata/templates/case_study_template.docx", out)

    content = open(written, encoding="utf-8").read()
    assert record["client"] not in content, \
        "the real client name leaked into a published document — spec section 7"


# TODO(Ahmet): test that a record with a missing field renders "[MISSING]"
#              rather than crashing
