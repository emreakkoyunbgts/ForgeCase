"""
CONSOLE — Serhat

The web app over the whole pipeline.

    streamlit run console/console.py

Streamlit lets you build a real web app in pure Python. Every widget you add
returns a value — that is the whole model.
"""
import sys
from pathlib import Path

# so we can import `common` when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from common.services import ALL_SERVICES, call_service
from common.contract import load_corpus, client_label, has_outcomes
from generator.generator import generate
from verifier.verifier import verify
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

# ---------------------------------------------------------------------------
# TODO(Serhat) L2: add search + filters here.
#   domain = st.selectbox("Domain", ["All"] + sorted({r["domain"] for r in corpus}))
#   then filter `corpus` before showing it.
# ---------------------------------------------------------------------------

st.subheader(f"{len(corpus)} engagements")

# --- the list -------------------------------------------------------------
labels = [f"{r['id']} — {client_label(r)} ({r['domain']}, {r['region']})"
          for r in corpus]
choice = st.selectbox("Pick an engagement", labels)
record = corpus[labels.index(choice)]

# --- the detail -----------------------------------------------------------
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
        # TODO(Serhat): eng-12 lands here. Make this look deliberate, not broken.
        st.warning("No measurable outcome was recorded for this engagement.")

with right:
    # CONFIDENTIALITY BADGE — this is your L2 ticket
    if record["may_be_named"]:
        st.success("✓ Client may be named")
    else:
        st.info("🔒 Anonymised — the real client name must not be used")

    st.metric("Region", record["region"])
    st.metric("Domain", record["domain"])

# --- generate -------------------------------------------------------------
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
        st.divider()
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
st.subheader("Service health")

for name, url in ALL_SERVICES.items():
    try:
        call_service("GET", url + "/health", timeout=3)
        st.success(f"{name}: OK")
    except Exception as e:
        st.warning(f"{name}: unreachable ({e})")




    
    
    



    
    
    
    
    
    
