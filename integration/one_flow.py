

import logging

from common.contract import load_corpus
from generator.generator import generate_one_source_single_stream_case_study
from librarian.librarian import search
from publisher.publisher import render_docx
from reader.reader import extract_record
from vault.vault import store
from verifier.verifier import verify

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("one_flow_log",encoding="utf-8"),
                              logging.StreamHandler()])

logger=logging.getLogger(__name__)



def do_research():
    logger.info("Starting research...")
    #İLETİŞİME GEÇİNCE EKLENECEK
    #search("stub_query", load_corpus(), top_k=3)
    return "Research completed successfully."

def do_analysis():
    logger.info("Starting analysis...")
    #generate_action_list()
    return "Analysis completed successfully."


def one_flow_stub():
    """
    This function represents a single flow of operations.
    It can be expanded to include more complex logic as needed.
    """
    print("Executing one flow of operations...")
    logger.info("Starting one flow of operations.")

    one_source_record=extract_record("stub_text", "stub_source")
    logger.info(f"Extracted record: {one_source_record}")
    store(one_source_record)
    logger.info("Record stored successfully.")
    case_study=generate_one_source_single_stream_case_study(one_source_record)
    logger.info(f"Generated case study: {case_study}")
    out_put=verify(case_study, one_source_record)
    logger.info(f"Verification result: {out_put}")

    render=render_docx(case_study,"caseforge-testdata/templates/case_study_template.docx" ,"output.docx")
    logger.info("Rendered case study to output.docx successfully. path: "+str(render))


    result = "Flow completed successfully."
    return result

