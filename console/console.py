"""
CONSOLE — Serhat

The web app over the whole pipeline.

    streamlit run console/console.py

Streamlit lets you build a real web app in pure Python. Every widget you add
returns a value — that is the whole model.
"""
import sys
from pathlib import Path
import uuid

# so we can import `common` when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from common.contract import load_corpus, client_label, has_outcomes
from generator.generator import generate
from verifier.verifier import verify
from common.services import ALL_SERVICES, call_service

st.set_page_config(page_title="CaseForge", page_icon="📄", layout="wide")

import json
from datetime import datetime, timezone

REVIEW_STATE_PATH = Path(__file__).resolve().parent / "review_state.json"


def load_review_state() -> dict:
    if not REVIEW_STATE_PATH.exists():
        return {}
    with open(REVIEW_STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_review_state(state: dict) -> None:
    with open(REVIEW_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
st.title("CaseForge")
st.caption("Turn a finished engagement into a case study — without inventing anything.")

corpus = load_corpus()

st.subheader(f"{len(corpus)} engagements")

labels = [f"{r['id']} — {client_label(r)} ({r['domain']}, {r['region']})"
          for r in corpus]
choice = st.selectbox("Pick an engagement", labels)
record = corpus[labels.index(choice)]

left, right = st.columns([2, 1])

with left:
    st.markdown(f"### {client_label(record)}")
    st.markdown(f"**Challenge**\n\n{record['challenge']}")
    st.markdown(f"**What we did**\n\n{record['solution']}")
    st.markdown(f"**Technology:** {', '.join(record['technologies'])}")

    st.markdown("**Outcomes**")
    if has_outcomes(record):
        for o in record["outcomes"]:
            st.markdown(f"- {o['metric']}  \n  <sub>source: {o['source_ref']}</sub>",
                        unsafe_allow_html=True)
    else:
        st.warning("No measurable outcome was recorded for this engagement.")

with right:
    if record["may_be_named"]:
        st.success("✓ Client may be named")
    else:
        st.info("🔒 Anonymised — the real client name must not be used")

    st.metric("Region", record["region"])
    st.metric("Domain", record["domain"])

st.divider()

engagement_id = record["id"]
state = load_review_state()
saved = state.get(engagement_id)

case_study = None
if saved is not None and "case_study" in saved:
    case_study = saved["case_study"]

elif st.button("Generate case study", type="primary"):
    with st.spinner("Generating..."):
        case_study = generate(record)
        state[engagement_id] = {"case_study": case_study}
        save_review_state(state)

if case_study is not None:
    st.subheader(case_study["title"])

    edited = {}
    for name, text in case_study["sections"].items():
        edited[name] = st.text_area(name.title(), value=text)

    if st.button("Save edits"):
        case_study["sections"] = edited
        state[engagement_id] = {"case_study": case_study}
        save_review_state(state)
        st.success("Kaydedildi.")
        st.rerun()

    st.subheader("Grounding check")
    report = verify(case_study, record)
    verdict_ok = report["verdict"] == "PASS"
    if verdict_ok:
        st.success("PASS - grounded")
    if not verdict_ok:
        st.error(f"BLOCK - {len(report['problems'])} problem(s) found")
        for p in report["problems"]:
            st.write(str(p))
st.divider()

current_status = state.get(engagement_id, {}).get("approved", False)
approved = st.checkbox("Approve — ready to publish", value=current_status)

if approved != current_status:
    if engagement_id not in state:
        state[engagement_id] = {}
    state[engagement_id]["approved"] = approved
    save_review_state(state)
    st.rerun()

if approved:
    st.success("Approved.")
    st.button("Download PDF", type="primary")
else:
    st.warning("Draft — pending approval.")
    st.button("Download PDF", disabled=True, help="Approve first to unlock download.")

st.divider()
st.header("🩺 System Health Dashboard")

if "last_errors" not in st.session_state:
    st.session_state.last_errors = {}

cols = st.columns(len(ALL_SERVICES))
for col, (name, url) in zip(cols, ALL_SERVICES.items()):
    with col:
        try:
            response = call_service("GET", url + "/health", timeout=3)
            elapsed = response.elapsed.total_seconds()
            if elapsed < 2:
                st.markdown(f"🟢 **{name}**")
                st.caption("healthy")
            else:
                st.markdown(f"🟡 **{name}**")
                st.caption(f"slow ({elapsed:.1f}s)")
            st.caption(f"latency: {elapsed * 1000:.0f} ms")
        except Exception as e:
            st.session_state.last_errors[name] = str(e)
            st.markdown(f"🔴 **{name}**")
            st.caption("unreachable")

        last_err = st.session_state.last_errors.get(name)
        if last_err:
            st.caption(f"⚠️ last error: {last_err[:60]}")

st.divider()
st.header("Upload a document (full pipeline via HTTP)")

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"], key="cf97_upload")

if uploaded_file is not None:
    st.write(f"Uploaded: {uploaded_file.name}")

    if st.button("Run pipeline (HTTP)"):
        pipeline_record = None
        run_correlation_id = str(uuid.uuid4())
        st.info(f"🔗 Correlation ID for this run: `{run_correlation_id}`")
        try:
            with st.spinner("Calling Reader..."):
                files = {"document": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                reader_response = call_service("POST", ALL_SERVICES["reader"] + "/extract", files=files, correlation_id=run_correlation_id)
                pipeline_record = reader_response.json()
                st.success(f"Reader extracted: {pipeline_record['id']}")
                st.json(pipeline_record)
        except Exception as e:
            st.error(f"Reader failed: {e}")

        if pipeline_record is not None:
            try:
                with st.spinner("Storing in Vault..."):
                    vault_response = call_service(
                        "POST", ALL_SERVICES["vault"] + "/engagements",
                        json=pipeline_record,
                        correlation_id=run_correlation_id,
                    )
                    st.success(f"Stored in Vault: {pipeline_record['id']}")
            except Exception as e:
                st.warning(f"Vault storage skipped: {e}")

        mcs = None
        if pipeline_record is not None:
            try:
                with st.spinner("Calling Generator..."):
                    mcs_payload = call_service(
                        "POST", ALL_SERVICES["generator"] + "/generator/mcs/eng",
                        json=pipeline_record,
                        correlation_id=run_correlation_id,
                    )
                    mcs = mcs_payload.json()
                    st.success("Generator produced multi-source content")
                    st.json(mcs)
            except Exception as e:
                st.error(f"Generator failed: {e}")

        verdict = None
        if mcs is not None:
            try:
                with st.spinner("Calling Verifier..."):
                    verify_payload = {"record": pipeline_record, "mcs": mcs}
                    verify_response = call_service(
                        "POST",
                        ALL_SERVICES["verifier"] + f"/verify/{pipeline_record['id']}",
                        json=verify_payload,
                        correlation_id=run_correlation_id,
                    )
                    verdict = verify_response.json()
                    if verdict["verdict"] == "PASS":
                        st.success("Verifier: PASS — every claim is grounded")
                    else:
                        st.error(f"Verifier: BLOCK — {len(verdict['problems'])} problem(s)")
                        for p in verdict["problems"]:
                            st.write(str(p))
            except Exception as e:
                st.error(f"Verifier failed: {e}")

        if verdict is not None and verdict.get("verdict") == "PASS":
            try:
                with st.spinner("Calling Publisher..."):
                    pub_response = call_service(
                        "POST", ALL_SERVICES["publisher"] + "/publish",
                        json={"record_id": pipeline_record["id"]},
                        correlation_id=run_correlation_id,
                    )
                    doc_path = pub_response.json()["path"]
                    st.success(f"Document ready: {doc_path}")
            except Exception as e:
                st.error(f"Publisher failed: {e}")
