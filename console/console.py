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

from common.contract import load_corpus, client_label, has_outcomes
from generator.generator import generate

st.set_page_config(page_title="CaseForge", page_icon="📄", layout="wide")

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

if st.button("Generate case study", type="primary"):
    with st.spinner("Generating..."):
        case_study = generate(record)

    st.subheader(case_study["title"])
    for name, text in case_study["sections"].items():
        st.markdown(f"**{name.title()}**\n\n{text}")

    # TODO(Serhat) L3:
    #   - an "Approve" checkbox. Download stays DISABLED until it is ticked.
    #     Nothing gets published without a human saying yes.
    #   - a "Download PDF" button that calls Ahmet's publisher
    st.info("TODO: add an Approve step, then a Download PDF button.")
