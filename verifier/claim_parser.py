import re
import json
from pathlib import Path
from typing import List, Dict, Any

class ClaimParser:
    """
    CaseForge L4 - Claim Level Parser (CF-58)
    Splits case study prose into checkable atomic factual assertions
    """

    def __init__(self):
        pass

    def split_into_sentences(self, text: str) -> List[str]:
        """
        Parse the text into sentences according to punctuation marks
        """
        try:
            if not text or not isinstance(text, str):
                return []

            # Basic sentence parser
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            return [s.strip() for s in sentences if s.strip()]
        except Exception:
            return []

    def extract_atomic_claims(self, sentence: str) -> List[Dict[str, Any]]:
        """
        Splits a sentence into atomic claims
        """
        try:
            if not sentence or not isinstance(sentence, str):
                return []

            claims = []

            # 1. Numeric / Metric Claims (Percentages, Numbers, Durations)
            # Ex: "reduced payment latency by 45%"
            metrics = re.findall(r'(\b\d+(?:\.\d+)?%?|\b\d+\s+(?:months?|years?|days?|hours?|minutes?)\b)', sentence, re.IGNORECASE)

            for m in metrics:
                claims.append({
                    "type": "metric_claim",
                    "raw_text": sentence,
                    "target_value": m,
                    "verified": False
                })
            
            # 2. Customer / Organisation Claims (Anonymization or Real Name)
            # Definitions like customer name or 'a Tier-1 GCC bank' 
            if "bank" in sentence.lower() or "client" in sentence.lower():
                claims.append({
                    "type": "client_claim",
                    "raw_text": sentence,
                    "verified": False
                })

            # 3. Qualitative Claims ( Genereal Assertions / Outcomes )
            if not metrics:
                claims.append({
                    "type": "qualitative_claim",
                    "raw_text": sentence,
                    "verified": False
                })

            return claims
        except Exception:
            return []

    def parse_case_study(self, case_study_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scans the all of the case_study JSON and returns an atomic claims list
        """
        try:
            if not case_study_data or not isinstance(case_study_data, dict):
                return []

            all_claims = []

            # Main text areas in the case study (challenge, solution, approach etc.)
            text_fields = ["challenge", "solution", "approach", "outcomes", "narrative", "summary",
            "solution_and_architecture", "results_and_outcomes", "background", "context"]

            for field in text_fields:
                if field in case_study_data:
                    content = case_study_data[field]
                    if isinstance(content, str):
                        sentences = self.split_into_sentences(content)
                        for sent in sentences:
                            claims = self.extract_atomic_claims(sent)
                            for c in claims:
                                c["field"] = field
                                all_claims.append(c)
                    elif isinstance(content, list):
                        for item in content:
                            text = str(item)
                            sentences = self.split_into_sentences(text)
                            for sent in sentences:
                                claims = self.extract_atomic_claims(sent)
                                for c in claims:
                                    c["field"] = field
                                    all_claims.append(c)

                if not all_claims:
                    for key, val in case_study_data.items():
                        if isinstance(val, str) and len(val) > 20:
                            for sent in self.split_into_sentences(val):
                                for claim in self.extract_atomic_claims(sent):
                                    claim["field"] = key
                                    all_claims.append(claim)

            return all_claims
        except Exception:
            return []

# -----------------------------------------------
# QUICK MANUEL TEST BLOCK (Running before the test file)
# -----------------------------------------------
if __name__ == "__main__":
    parser = ClaimParser()

    # 1. Testing with an Example Text
    sample_text = "The shadow migration was completed in 11 months for Gulf Union Bank. Payment latency was reduced by 45%."
    print("--- 1. Sentence Parsing Test ---")
    sentences = parser.split_into_sentences(sample_text)
    print(f"Catched Sentence Number: {len(sentences)}")
    for i, s in enumerate (sentences, 1):
        print(f" Sentence {i}: {s}")

    print("\n--- 2. Claim Parsing Test ---")
    for s in sentences:
        claims = parser.extract_atomic_claims(s)
        print(f"\nSentence: '{s}'")
        print(f"Claims: {claims}")

    # 2. Real JSON Testing
    sample_file = Path("caseforge-testdata/case_studies/eng-01_clean.json")
    if sample_file.exists():
        print("\n--- 3. Clean JSON File Test ---")
        with open(sample_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_claims = parser.parse_case_study(data)
        print(f"Total Number of Collected Atomic Claim: {len(all_claims)}")
        print("First 3 Claim Example:")
        print(json.dumps(all_claims[:3], indent=2))

    # 3. Normal Sentence Testing
    print("\n--- 4. Normal Sentence Test ---")
    s = "Payment latency was reduced by 45%."
    print("Claims: ", parser.extract_atomic_claims(s))

    print("\n--- 5. Edge Case / Crash Test ---")
    print("None Input: ", parser.extract_atomic_claims(None))
    print("Number Input: ", parser.extract_atomic_claims(12345))
    print("Empty Dict JSON: ", parser.parse_case_study({}))
    print("Invalid JSON Type: ", parser.parse_case_study("invalid_json_string"))
    print("\n[SUCCESS] All edge case tests completetd without any crash!")
