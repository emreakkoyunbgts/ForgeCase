"""
GENERATOR — Taha

Engagement Record -> grounded case study.

    python -m generator.generator <record.json>  > case_study.json

See the Project Specification, sections 3, 4.1 and 7.
"""
import argparse
import json
import sys

import textwrap
import os
import matplotlib
matplotlib.use('Agg')  # Arayüz/Pencere açılmasını engeller, tamamen sessiz çalışır

import matplotlib.pyplot as plt

from common.contract import load_record, client_label, has_outcomes
from common.llm import ask_for_json, GROUNDING_RULES

SYSTEM = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
"""




def save_case_study_to_pdf(case_study: dict, case_study_id: str, output_dir: str = "generator_case_study") -> str:
    """
    Case study sözlüğünü hiç gereksiz boşluk bırakmadan tam bir düz yazı / rapor formatında PDF olarak kaydeder.
    """
    # 1. Klasör Yolunu Hazırlama
    clean_dir = output_dir.strip("/")
    abs_output_dir = os.path.abspath(clean_dir)
    os.makedirs(abs_output_dir, exist_ok=True)

    file_name = f"case_study-{case_study_id}.pdf"
    file_path = os.path.join(abs_output_dir, file_name)

    # 2. Sözlükteki Tüm Veriyi Düz Metin (Plain Text) Haline Getirme
    title = str(case_study.get("title", "Case Study")).upper()
    eng_id = case_study.get("engagement_id", case_study_id)
    client_named = case_study.get("client_named", False)

    # Düz metin bloğunu inşa ediyoruz
    lines = []
    lines.append(f"{title}")
    lines.append(f"Engagement ID: {eng_id} | Client Named: {client_named}")
    lines.append("=" * 70)
    lines.append("")

    # Sections (Bölümler)
    sections = case_study.get("sections", {})
    for sec_name, sec_content in sections.items():
        if sec_content:
            lines.append(f"{sec_name.upper()}:")
            lines.append(f"{sec_content}")
            lines.append("")  # Bölümler arası sadece 1 satır boşluk

    # Citations (Kaynaklar)
    citations = case_study.get("citations", [])
    if citations:
        lines.append("CITATIONS:")
        for cite in citations:
            claim = cite.get('claim', '')
            source = cite.get('source_ref', 'N/A')
            lines.append(f"• {claim} [Source: {source}]")

    # Tüm satırları birleştirip tek bir düz yazı bloğu yapıyoruz
    full_text = "\n".join(lines)

    # 3. Matplotlib ile Tek Bir Metin Bloğu Olarak Basma
    # figsize yüksekliğini metin miktarına göre dinamik ayarlıyoruz
    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.axis('off')

    # va='top' sayesinde metin en tepeden başlar, aşağıya doğru akar
    ax.text(
        0.05, 0.95, full_text,
        transform=ax.transAxes,
        fontsize=9.5,
        fontfamily='monospace', # Monospace font sayesinde düzgün hiza
        verticalalignment='top',
        wrap=True
    )

    # 4. Kaydet ve Kapat
    plt.savefig(file_path, format="pdf", bbox_inches="tight", pad_inches=0.4)
    plt.close(fig)

    return file_path


def render_outcomes(record):
    outcomes = record.get("outcomes")

    if not outcomes:
        return "[MISSING: no measurable outcome was recorded for this engagement]"

    parts = []

    for outcome in outcomes:
        metric = outcome.get("metric")

        if not metric:
            parts.append("[MISSING: outcome metric]")
        else:
            parts.append(metric)

    return "; ".join(parts)


def render_citations(record):
    citations = []

    for outcome in record.get("outcomes", []):

        metric = outcome.get("metric")
        source_ref = outcome.get("source_ref")

        if not metric:
            citations.append({
                "claim": "[MISSING: outcome metric]",
                "source_ref": "[MISSING: source reference required]"
            })

        if not source_ref:
            citations.append({
                "claim": metric,
                "source_ref": "[MISSING: source reference required]"
            })
        else:
            citations.append({
                "claim": metric,
                "source_ref": source_ref
            })

    return citations

def render_challenge(record):
    return (
        record.get("challenge")
        or "[MISSING: challenge description]"
    )

def render_solution(record):
    return (
        record.get("solution")
        or "[MISSING: solution description]"
    )

def render_technology(record):
    technologies = record.get("technologies")

    if not technologies:
        return "[MISSING: technologies used]"

    return ", ".join(technologies)

def render_team_size(record):
    return (
        str(record["team_size"])
        if record.get("team_size") is not None
        else "[MISSING: team size]"
    )

def render_title(record):
    domain = record.get("domain")

    if not domain:
        domain = "[MISSING: domain]"

    return f"{domain} for {client_label(record)}"

def render_context(record):
    region = record.get("region") or "[MISSING: region]"

    return f"{client_label(record)} in {region}."


def generate(record):
    """
    Turn a record into a case study.

    TODO(Taha) L1: prompt the LLM with the record, get the five sections back.
    TODO(Taha) L2: enforce grounding.
        - if has_outcomes(record) is False, the outcomes section MUST say
          something like "[MISSING: no measurable outcome recorded]" and MUST
          NOT contain a number. This is the single most important test in the
          project — eng-12 exists precisely to catch you inventing one.
        - ALWAYS use client_label(record), never record["client"] directly.
    TODO(Taha) L3: add citations[] linking each claim to its source_ref.
    """
    # --- STUB: replace me -------------------------------------------------
    print(f"[generator] STUB: fabricating nothing, echoing the record",
          file=sys.stderr)
    """
    outcomes_text = (
        "; ".join(o["metric"] for o in record["outcomes"])
        if has_outcomes(record)
        else "[MISSING: no measurable outcome was recorded for this engagement]"
    )
    """
    cs={
        "engagement_id":  record.get("id", "[MISSING: engagement id]"),
        "title": render_title(record),
        "sections": {
            "context": render_context(record),
            "challenge": render_challenge(record),
            "approach": render_solution(record),
            "technology": render_technology(record),
            "outcomes": render_outcomes(record),
        },
        "citations": render_citations(record),
        "client_named": record.get("may_be_named", False),
    }
    save_path=save_case_study_to_pdf(cs, cs["engagement_id"])
    print(f"[generator] Case study saved to: {save_path}", file=sys.stderr)
    return cs
    # ----------------------------------------------------------------------

def get_five_sections_with_llm(record):
    """
    Use the LLM to generate the five sections of a case study.

    This is the core of the generator. It is a single LLM call, with a
    system prompt that enforces grounding and a user prompt that contains
    the record.

    The LLM must return JSON with five sections: context, challenge, approach,
    technology, outcomes. Each section must be grounded in the record.
    """
    user_prompt = f"Record:\n{json.dumps(record, indent=2 , ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record."

    response = ask_for_json(SYSTEM, user_prompt)
    return response

def main():
    parser = argparse.ArgumentParser(description="Record -> case study")
    parser.add_argument("record", help="path to an engagement record")
    args = parser.parse_args()

    record = load_record(args.record)
    case_study = generate(record)

    json.dump(case_study, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
