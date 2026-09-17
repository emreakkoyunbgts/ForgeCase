"""CaseForge Console: every business operation crosses an HTTP boundary."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from copy import deepcopy
import streamlit as st
from common.drafts import SECTION_FIELDS
from common.services import ALL_SERVICES, call_service
from console.workflow import Workflow

st.set_page_config(page_title="CaseForge", page_icon="📄", layout="wide")
st.title("CaseForge")
st.caption("Choose a source, review a grounded draft and publish after verification.")

if "workflow" not in st.session_state:
    st.session_state.workflow = Workflow()
    st.session_state.generation = 0
workflow = st.session_state.workflow

def clear_ui_approval():
    st.session_state.approval = False
    st.session_state.pop("document_bytes", None)
    st.session_state.pop("provenance_bytes", None)

def act(label, action):
    try:
        with st.spinner(label):
            return action()
    except Exception as exc:
        st.error(str(exc))
        return None

st.header("1. Source")
records = act("Loading Vault records…", workflow.list_records)
records = records or []
record_map = {record["id"]: record for record in records}
choices = ["", *record_map]
if workflow.record_id and workflow.record_id not in choices:
    choices.append(workflow.record_id)
selected = st.selectbox("Engagement in Vault", choices, index=choices.index(workflow.record_id),
    format_func=lambda value: "Choose an engagement" if not value else
    f"{value} — {record_map.get(value, {}).get('client_type', '')}")
if selected != workflow.record_id:
    workflow.select(selected)
    clear_ui_approval()

uploaded = st.file_uploader("Or upload a structured closeout PDF", type=["pdf"])
st.caption("Text-layer PDF with an Engagement ID, labelled fields and numbered sections.")
if st.button("Extract and store", disabled=uploaded is None):
    result = act("Extracting and storing…", lambda: workflow.extract(uploaded.name, uploaded.getvalue()))
    clear_ui_approval()
    if result:
        st.success(f"Stored {result['id']} in Vault.")
        st.rerun()
    elif workflow.last_extracted:
        st.json(workflow.last_extracted)
if workflow.record_id in record_map:
    record = record_map[workflow.record_id]
    st.info(f"{record['client'] if record['may_be_named'] else record['client_type']} · "
            f"{record['domain']} · {record['region']}")
    if not record["may_be_named"]:
        st.caption("Anonymous client — the real name cannot appear in the document.")

st.header("2. Draft")
language = st.selectbox("Language", ["en", "de", "tr"], index=["en","de","tr"].index(workflow.language),
                       format_func=lambda value: {"en":"English", "de":"Deutsch", "tr":"Türkçe"}[value])
if language != workflow.language:
    workflow.select(workflow.record_id, language)
    clear_ui_approval()

if st.button("Generate draft", disabled=not workflow.record_id, type="primary"):
    result = act("Generating…", workflow.generate)
    clear_ui_approval()
    if result:
        st.session_state.generation += 1

if workflow.draft is not None:
    edited = deepcopy(workflow.draft)
    prefix = f"{workflow.record_id}-{workflow.language}-{st.session_state.generation}"
    for i, title in enumerate(edited["titles"]):
        title["title"] = st.text_input("Title", value=title["title"], key=f"{prefix}-title-{i}")
    for section, field in SECTION_FIELDS.items():
        for i, entry in enumerate(edited["sections"][section]):
            entry[field] = st.text_area(section.title(), value=entry[field], key=f"{prefix}-{section}-{i}")
    if edited != workflow.draft:
        workflow.edit(edited)
        clear_ui_approval()
    with st.expander("Source references"):
        for citation in workflow.draft["citations"]:
            st.write(citation["claim"])
            st.caption(citation["source_ref"])

st.header("3. Verify and approve")
if st.button("Verify draft", disabled=workflow.draft is None):
    clear_ui_approval()
    act("Verifying against the Vault source…", workflow.verify)
if workflow.report:
    if workflow.verified:
        st.success("PASS — every assessed claim is supported.")
    else:
        st.error("BLOCK — publication is unavailable.")
        for problem in workflow.report["problems"]:
            st.write(problem.get("why") or problem.get("detail") or problem.get("type"))
            if problem.get("value"):
                st.caption(str(problem["value"]))
approval = st.checkbox("I have reviewed this draft and approve publication.",
                       key="approval", disabled=not workflow.verified)
workflow.approve(approval and workflow.verified)
st.caption("Editing the draft or changing its language clears verification and approval.")

st.header("4. Publish and download")
format = st.selectbox("Format", ["docx", "pdf"])
layout = st.selectbox("Layout", ["full-case-study", "one-pager", "single-slide"]) if format == "pdf" else "full-case-study"
if st.button("Publish document", disabled=not workflow.approved):
    st.session_state.pop("document_bytes", None)
    st.session_state.pop("provenance_bytes", None)
    result = act("Publisher is verifying and rendering…", lambda: workflow.publish(format, layout))
    if result:
        st.session_state.document_bytes = act("Downloading document…", workflow.download)
        st.session_state.provenance_bytes = act("Downloading provenance…", lambda: workflow.download(True))
if workflow.artifact and st.session_state.get("document_bytes") is not None:
    st.success(f"Ready: {workflow.artifact['filename']}")
    st.download_button("Download document", st.session_state.document_bytes,
                       workflow.artifact["filename"], workflow.artifact["media_type"], on_click="ignore")
    if st.session_state.get("provenance_bytes") is not None:
        st.download_button("Download provenance", st.session_state.provenance_bytes,
                           "provenance.json", "application/json", on_click="ignore")

st.caption(f"Correlation ID: {workflow.trace}")
with st.expander("Service availability"):
    if st.button("Check services"):
        for name, base_url in ALL_SERVICES.items():
            try:
                call_service("GET", base_url + "/health", timeout=3, headers=workflow.headers())
                st.write(f"{name}: available")
            except Exception:
                st.write(f"{name}: unavailable")
