import json
import os
import logging
import sys

from common.llm import ask_for_json
from generator.generator import generate_multi_source, get_five_sections_with_llm, get_llm_punchy

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("generator_analysis.log",encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])

logger=logging.getLogger(__name__)

SYSTEM_JUDGE="""
you are a text judge , I am gone give you 2 type jsons 
one has sources other is result output from LLM 
they contain many documents , 
you will match each document from source with the result output with id.
then you will give me faithfulness and coverage score for each document for all documents.
give me a json output with id, faithfulness and coverage score for each document.
"""



def save_llm_evaluation_to_json(
    llm_response: list[dict],
    output_dir: str = "generator_analysis"
) -> str:

    os.makedirs(output_dir, exist_ok=True)

    i = 1

    while True:
        file_name = f"evaluation_{i}.json"
        output_path = os.path.join(output_dir, file_name)

        if not os.path.exists(output_path):
            break

        i += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            llm_response,
            f,
            indent=4,
            ensure_ascii=False
        )

    return output_path

def load_default_result(id :str , record: dict ,path="generator_llm_output_json"):
    """
    Load the default result JSON file.
    """
    file_name=f"['{id}'].json"
    file_path = os.path.join(path, file_name)
    try:
        with open(file_path, encoding="utf-8") as f:
            logger.info(f"loading file {file_name} from path {path}")
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Result file not found at {path} — starting LLM generation for record {id}")

        mcs=generate_multi_source([record])
        llm_output=get_five_sections_with_llm(mcs)
        logger.info(f"Generated LLM output for record {id}")

        return llm_output
    except json.JSONDecodeError as e:
        logger.error(f"{path} is not valid JSON: {e}")
        return None


def load_punchy_result(id :str , record: dict ,path="generator_llm_output_json"):
    """
    Load the default result JSON file.
    """
    ###DEĞİŞECEK ADA GÖRE DÜZENLENECEK
    file_name=f"['{id}']_punchy.json"
    file_path = os.path.join(path, file_name)
    try:
        with open(file_path, encoding="utf-8") as f:
            logger.info(f"loading file {file_name} from path {path}")
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Result file not found at {path} — starting LLM generation for record (punchy) {id}")

        mcs=generate_multi_source([record])
        llm_output=get_llm_punchy(mcs)
        logger.info(f"Generated Punchy LLM output for record {id}")

        return llm_output
    except json.JSONDecodeError as e:
        logger.error(f"{path} is not valid JSON: {e}")
        return None

def load_concise_result(id :str , record: dict ,path="generator_llm_output_json"):
    """
    Load the default result JSON file.
    """
    ###DEĞİŞECEK ADA GÖRE DÜZENLENECEK
    file_name=f"['{id}']_concise.json"
    file_path = os.path.join(path, file_name)
    try:
        with open(file_path, encoding="utf-8") as f:
            logger.info(f"loading file {file_name} from path {path}")
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Result file not found at {path} — starting LLM generation for record (concise) {id}")

        mcs=generate_multi_source([record])
        llm_output=get_llm_punchy(mcs)
        logger.info(f"Generated Concise LLM output for record {id}")

        return llm_output
    except json.JSONDecodeError as e:
        logger.error(f"{path} is not valid JSON: {e}")
        return None


def analyze_default_outputs():
    """
    Analyze all datasets in the generator.
    """

    counter=0
    sources=[]
    results=[]


    for filename in os.listdir("caseforge-testdata/records/seed"):
        if filename.endswith(".json"):
            file_path = os.path.join("caseforge-testdata/records/seed", filename)
            print(f"Analyzing {file_path}...")
            # Here you would implement the logic to analyze each dataset
            # For example, you might load the JSON and perform some checks
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                    record_id=record.get("id", "unknown")

                    logger.info(f"Analyzing record with ID: {record_id}")
                    sources.append(record)
                    result=load_default_result(record_id, record)
                    results.append(result)
                    counter+=1




            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {file_path}: {e}")
            except FileNotFoundError as e:
                logger.error(f"File not found {file_path}: {e}")

    logger.info(f"Total records analyzed so far: {counter}")

    sources_string=json.dumps(sources, indent=2, ensure_ascii=False)
    results_string=json.dumps(results, indent=2, ensure_ascii=False)

    user_promt=f"sources: {sources_string} \n results: {results_string} \n "

    response=ask_for_json(SYSTEM_JUDGE, user_promt)
    logger.info(f"Analysis response: {response}")
    path=save_llm_evaluation_to_json(response)
    logger.info(f"Saved LLM evaluation to {path}")

    return response


