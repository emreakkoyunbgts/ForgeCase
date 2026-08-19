"""
GENERATOR — Taha

Engagement Record -> grounded case study.

    python -m generator.generator <record.json>  > case_study.json

See the Project Specification, sections 3, 4.1 and 7.
"""
import argparse
import asyncio
import json
import sys

import textwrap
import os
import time

import matplotlib
matplotlib.use('Agg')  # Arayüz/Pencere açılmasını engeller, tamamen sessiz çalışır

import matplotlib.pyplot as plt

from common.contract import load_record, client_label, has_outcomes
from common.llm import ask_for_json, GROUNDING_RULES

import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)





SYSTEM_CHECK="""
you are a text comprator, there is rules; 
""" + GROUNDING_RULES + """

I am gone give you 2 json document one is source which is multi source case ,
another is text to be checked which is LLM output,
don't Text correction! Only remove incorrect or fabricated information.
Do not add any text or information.just compare with source json .
"""


SYSTEM = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.
Keep it factual and professional. No marketing language.
"""

SYSTEM_TAHA="""You are a analytical AI assistant that generates case studies for BGTS, 
a software consultancy that serves banks.


""" + GROUNDING_RULES + """
Write five sections: context, challenge, approach, technology, outcomes.
Write with highlighting the developed features .
Keep it factual and professional. No marketing language.

"""

SYSTEM_CONCISE = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.

Tone:
- Concise and direct.
- Use short paragraphs and straightforward wording.
- Prioritize clarity over detail.
- Keep every sentence information-dense.

The requested tone must never override the grounding rules.
"""

SYSTEM_PUNCHY = """You write case studies for BGTS, a software consultancy that
serves banks.

""" + GROUNDING_RULES + """

Write five sections: context, challenge, approach, technology, outcomes.

Tone:
- Crisp and engaging while remaining professional.
- Vary sentence structure to improve readability.
- Prefer active voice.
- Make the narrative flow naturally without adding facts.
- Never exaggerate impact or use promotional language.

The requested tone must never override the grounding rules.
"""






def save_llm_output_as_json(llm_output: dict,
                            case_study_id: str,
                            output_dir: str = "generator_llm_output_json") -> str:
    """
    Saves a generated case study dictionary as a JSON file.

    Returns:
        Path to the saved JSON file.
    """
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, f"{case_study_id}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            llm_output,
            f,
            indent=4,
            ensure_ascii=False
        )

    return output_path






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


def save_llm_output_to_pdf(
    llm_output: dict,
    output_id: str,
    output_dir: str = "generator_llm_output"
) -> str:
    """
    LLM çıktısını düz yazı / rapor formatında PDF olarak kaydeder.
    """

    import os
    import matplotlib.pyplot as plt

    # 1. Klasör Yolunu Hazırlama
    clean_dir = output_dir.strip("/")
    abs_output_dir = os.path.abspath(clean_dir)
    os.makedirs(abs_output_dir, exist_ok=True)

    file_name = f"llm_output-{output_id}.pdf"
    file_path = os.path.join(abs_output_dir, file_name)

    # 2. Metin Bloğunu Oluşturma
    lines = []

    lines.append("LLM OUTPUT")
    lines.append("=" * 70)
    lines.append("")

    for key, value in llm_output.items():

        lines.append(f"{key.upper()}:")

        # String alanlar
        if isinstance(value, str):
            lines.append(value)

        # Liste alanlar
        elif isinstance(value, list):

            if not value:
                lines.append("-")

            # List[str]
            elif all(isinstance(item, str) for item in value):
                for item in value:
                    lines.append(f"• {item}")

            # List[dict]
            elif all(isinstance(item, dict) for item in value):
                for item in value:
                    for field, field_value in item.items():
                        lines.append(f"{field}: {field_value}")
                    lines.append("")

            else:
                lines.append(str(value))

        # Dict alanlar
        elif isinstance(value, dict):
            for field, field_value in value.items():
                lines.append(f"{field}: {field_value}")

        # Diğer tipler
        else:
            lines.append(str(value))

        lines.append("")

    full_text = "\n".join(lines)

    # 3. PDF'e Yazdırma
    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.axis("off")

    ax.text(
        0.05,
        0.95,
        full_text,
        transform=ax.transAxes,
        fontsize=9.5,
        fontfamily="monospace",
        verticalalignment="top",
        wrap=True,
    )

    # 4. Kaydet
    plt.savefig(
        file_path,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.4,
    )

    plt.close(fig)
    logger.info(f"LLM output saved to: {file_path}")
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

###
######THIS AREA IS FOR MULTI-SOURCE CASE STUDY GENERATION######
###

def save_case_study_to_pdf_multi_source(
        case_study: dict,
        case_study_id: str,
        output_dir: str = "generator_multi_source_case_study"
) -> str:
    """
    Multi-source case study sözlüğünü PDF olarak kaydeder.
    Dict yapısını aynen korur, hiçbir alanı ayrıştırmaz.
    """

    # 1. Klasör hazırlama
    clean_dir = output_dir.strip("/")
    abs_output_dir = os.path.abspath(clean_dir)
    os.makedirs(abs_output_dir, exist_ok=True)

    file_name = f"case_study-{case_study_id}.pdf"
    file_path = os.path.join(abs_output_dir, file_name)

    # 2. Verileri al
    engagement_ids = case_study.get("engagement_ids", [])
    titles = case_study.get("titles", [])
    sections = case_study.get("sections", {})
    citations = case_study.get("citations", [])
    client_named = case_study.get("client_named", False)

    # 3. Metni oluştur
    lines = []

    lines.append("MULTI SOURCE CASE STUDY")
    lines.append(f"Engagement IDs: {', '.join(engagement_ids)}")
    lines.append(f"Client Named: {client_named}")
    lines.append("=" * 70)
    lines.append("")

    # Titles
    if titles:
        lines.append("TITLES:")
        for title in titles:
            lines.append(str(title))
        lines.append("")

    # Sections
    for section_name, values in sections.items():

        lines.append(f"{section_name.upper()}:")

        for value in values:
            lines.append(str(value))

        lines.append("")

    # Citations
    if citations:

        lines.append("CITATIONS:")

        for cite in citations:
            lines.append(str(cite))

    full_text = "\n".join(lines)

    # 4. PDF oluştur (eski görünüm)
    fig, ax = plt.subplots(figsize=(8.5, 7))

    ax.axis("off")

    ax.text(
        0.05,
        0.95,
        full_text,
        transform=ax.transAxes,
        fontsize=9.5,
        fontfamily="monospace",
        verticalalignment="top",
        wrap=True,
    )

    # 5. Kaydet
    plt.savefig(
        file_path,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.4,
    )

    plt.close(fig)
    logger.info(f"Multi-source case study saved to: {file_path}")
    return file_path




def render_multi_source_citations(record,id):
    citations = []

    for outcome in record.get("outcomes", []):

        metric = outcome.get("metric")
        source_ref = outcome.get("source_ref")

        if not metric:
            citations.append({
                "claim": "[MISSING: outcome metric]",
                "source_ref": "[MISSING: source reference required]",
                "page_ref": id
            })

        if not source_ref:
            citations.append({
                "claim": metric,
                "source_ref": "[MISSING: source reference required]",
                "page_ref": id
            })
        else:
            citations.append({
                "claim": metric,
                "source_ref": source_ref,
                "page_ref": id
            })

    return citations

def render_multi_source_outcomes(record,id):
    return {
        "outcomes":render_outcomes(record),
        "page" : id
    }
def render_multi_source_technology(record,id):
    return {
        "technologies":render_technology(record),
        "page" : id
    }
def render_multi_source_solution(record,id):
    return {
        "approach": record.get("solution") or "[MISSING: solution description]",
        "page" : id
    }
def render_multi_source_challenge(record,id):
    return {
        "challenge": record.get("challenge") or "[MISSING: challenge description]",
        "page" : id
    }

def render_multi_source_tite(record,name,id):
    domain = record.get("domain")

    if not domain:
        domain = "[MISSING: domain]"

    return {
        "title": f"{domain} for {name}",
        "page" : id
    }
def render_multi_source_context(record,name,id):
    region = record.get("region") or "[MISSING: region]"

    return {
        "region": f"{name} in {region}.",
        "page" : id
    }



def client_may_be_named(record):
    return record.get("may_be_named", False)

def generate_two_source(record1 , record2):
    r1_id = record1.get("id", "[MISSING: engagement id]")
    r2_id = record2.get("id", "[MISSING: engagement id]")
    may_be=client_may_be_named(record1) and client_may_be_named(record2)
    r1_name=""
    r2_name=""
    if(may_be):
        r1_name=record1.get("client", "[MISSING: client name]")
        r2_name=record2.get("client", "[MISSING: client name]")
    else:
        r1_name=record1.get("client_type", "[MISSING: client type]")
        r2_name=record2.get("client_type", "[MISSING: client type]")

    if r1_name != r2_name:
        print(f"[generator] WARNING: The two records have different client names/types: {r1_name} vs {r2_name}", file=sys.stderr)
    tcs = {
        "engagement_ids": [r1_id, r2_id],
        "titlies" : [render_multi_source_tite(record1,r1_name,r1_id), render_multi_source_tite(record2,r2_name,r2_id)],
        "sections": {
            "context": [render_multi_source_context(record1,r1_name,r1_id), render_multi_source_context(record2,r2_name,r2_id)],
            "challenge": [render_multi_source_challenge(record1,r1_id), render_multi_source_challenge(record2,r2_id)],
            "approach": [render_multi_source_solution(record1,r1_id), render_multi_source_solution(record2,r2_id)],
            "technology": [render_multi_source_technology(record1,r1_id), render_multi_source_technology(record2,r2_id)],
            "outcomes": [render_multi_source_outcomes(record1,r1_id), render_multi_source_outcomes(record2,r2_id)],
        },
        "citations": render_multi_source_citations(record1,r1_id) + render_multi_source_citations(record2,r2_id),
        "client_named": may_be,
    }

    print(f"[generator] Multi-source case study generated for records {r1_id} and {r2_id}", file=sys.stderr)
    print(f"[generator] Case study details: {tcs}", file=sys.stderr)

    return tcs




def generate_multi_source(records):
    start_time = time.perf_counter()
    if not records:
        logger.error("records list cannot be empty")
        raise ValueError("records list cannot be empty")

    engagement_ids = [
        record.get("id", "[MISSING: engagement id]")
        for record in records
    ]

    may_be = all(client_may_be_named(record) for record in records)
    logger.info(f"Client may be named: {may_be}")
    client_names = []

    for record in records:
        if may_be:
            client_names.append(
                record.get("client", "[MISSING: client name]")
            )
        else:
            client_names.append(
                record.get("client_type", "[MISSING: client type]")
            )

    domain1 = records[0].get("domain", "[MISSING: domain]")
    for record in records[1:]:
        domain = record.get("domain", "[MISSING: domain]")
        if domain != domain1:
            logger.warning(f"Different domains found: {domain1} vs {domain}")
            print(
                f"[generator] WARNING: Different domains found: {domain1} vs {domain}",
                file=sys.stderr,
            )

    if len(set(client_names)) > 1:
        logger.warning(f"Different client names/types found: {client_names}")
        print(
            f"[generator] WARNING: Different client names/types found: {client_names}",
            file=sys.stderr,
        )

    tcs = {
        "engagement_ids": engagement_ids,

        "titles": [
            render_multi_source_tite(record, client_name, engagement_id)
            for record, client_name, engagement_id in zip(
                records,
                client_names,
                engagement_ids,
            )
        ],

        "sections": {
            "context": [
                render_multi_source_context(record, client_name, engagement_id)
                for record, client_name, engagement_id in zip(
                    records,
                    client_names,
                    engagement_ids,
                )
            ],

            "challenge": [
                render_multi_source_challenge(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "approach": [
                render_multi_source_solution(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "technology": [
                render_multi_source_technology(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],

            "outcomes": [
                render_multi_source_outcomes(record, engagement_id)
                for record, engagement_id in zip(records, engagement_ids)
            ],
        },

        "citations": [
            citation
            for record, engagement_id in zip(records, engagement_ids)
            for citation in render_multi_source_citations(record, engagement_id)
        ],

        "client_named": may_be,
    }

    print(
        f"[generator] Multi-source case study generated for records {engagement_ids}",
        file=sys.stderr,
    )

    print(f"[generator] Case study details: {tcs}", file=sys.stderr)

    save_path = save_case_study_to_pdf_multi_source(tcs, ",".join(tcs["engagement_ids"]))
    print(f"[generator] Case study saved to: {save_path}", file=sys.stderr)
    end_time=time.perf_counter()
    logger.info(f"Multi-source case study generation time: {end_time-start_time:.2f} seconds")

    return tcs









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
    start_time=time.perf_counter()
    user_prompt = f"Record:\n{json.dumps(record, indent=2 , ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given record."

    response = ask_for_json(SYSTEM, user_prompt)
    logger.info(f"LLM response: {response}")
    pdf_name = ",".join(record["engagement_ids"])
    path =  save_llm_output_to_pdf(response, pdf_name)
    logger.info(f"LLM output saved to: {path}")
    end_time=time.perf_counter()
    logger.info(f"LLM processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response,record["engagement_ids"])
    logger.info(f"LLM output saved to JSON: {json_path}")

    return response


def get_llm_punchy(mcs: dict):
    start_time=time.perf_counter()
    user_prompt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given multi-source case study and provide a punchy summary."

    response =ask_for_json(SYSTEM_PUNCHY, user_prompt)
    logger.info(f"LLM punchy response: {response}")
    pdf_name = ",".join(mcs["engagement_ids"]) + "_punchy"
    path = save_llm_output_to_pdf(response, pdf_name)
    logger.info(f"LLM punchy output saved to: {path}")
    end_time=time.perf_counter()
    logger.info(f"LLM punchy processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_punchy")
    logger.info(f"LLM punchy output saved to JSON: {json_path}")


    return response


def get_llm_concise(mcs: dict):
    start_time=time.perf_counter()
    user_prompt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_prompt += "Analyze the given multi-source case study and provide a concise summary."

    response = ask_for_json(SYSTEM_CONCISE, user_prompt)
    logger.info(f"LLM concise response: {response}")
    pdf_name=",".join(mcs["engagement_ids"])+"_concise"
    path=save_llm_output_to_pdf(response, pdf_name)
    logger.info(f"LLM concise output saved to: {path}")
    end_time=time.perf_counter()
    logger.info(f"LLM concise processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_concise")
    logger.info(f"LLM concise output saved to JSON: {json_path}")

    return response


def chech_llm_output_with_source(mcs, llm_output):
    start_time=time.perf_counter()
    user_promt = f"Multi-source case study:\n{json.dumps(mcs, indent=2, ensure_ascii=False)}\n\n"
    user_promt += f"LLM output:\n{json.dumps(llm_output, indent=2, ensure_ascii=False)}\n\n"
    user_promt += "Compare the LLM output with the multi-source case study and remove any incorrect or fabricated information. "


    response=ask_for_json(SYSTEM_CHECK, user_promt)
    logger.info(f"LLM check response: {response}")
    pdf_name=",".join(mcs["engagement_ids"])+"_check"
    path=save_llm_output_to_pdf(response, pdf_name)
    logger.info(f"LLM check output saved to: {path}")
    end_time=time.perf_counter()
    logger.info(f"LLM check processing time: {end_time-start_time:.2f} seconds")

    json_path=save_llm_output_as_json(response, ",".join(mcs["engagement_ids"])+"_check")
    logger.info(f"LLM check output saved to JSON: {json_path}")

    return response


def generate_single_stream(records):

    mcs=generate_multi_source(records)
    llm_out=get_five_sections_with_llm(mcs)
    last_output=chech_llm_output_with_source(mcs,llm_out)
    #path=save_llm_output_to_pdf(llm_out, ",".join(mcs["engagement_ids"]))
    #logger.info(f"LLM output saved to: {path}")
    return last_output

def generate_one_source_single_stream_case_study(record):
    mcs=generate_multi_source([record])
    llm_out=get_five_sections_with_llm(mcs)
    last_output=chech_llm_output_with_source(mcs,llm_out)

    #return last_output
    return mcs



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
