############## NEW VERSION ##################

"""
CF-59: Entailment Checker Module
Validates claims extracted from drafts against ground-truth records.
"""
import re

QUALITATIVE_CLAIM_PATTERNS = [
        r"\bhuge\s+success\b",
        r"\bdramatically\b",
        r"\bunprecedented\b",
        r"\bmassive\s+(increase | growth | reduction)\b",
        r"\brevolutionary\b",
        r"\bgroundbreaking\b",
        r"\bzero\s+delay\b",
        r"\bslashed\s+expenses\b",
        r"\bgame-changer\b",
        r"\bskyrocketed\b",
        r"\bsecond\s+to\s+none\b",
    ]

class EntailmentChecker:

    def __init__(self):
        pass

    def check_paraphrased_claims(self, claim_text: str, ground_truth: dict) -> list:
        """
        L4: Detects exaggerated or unsupported qualitative claims 
        (paraphrased inventions) within the text
        """
        problems = []
        text_lower = claim_text.lower()

        # 1. Semantic Regex/Pattern Control
        for pattern in QUALITATIVE_CLAIM_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                found_phrase = match.group(0)
                """
                # 2. Ground Truth Verification: Is there an explicit verification flag or metric
                 in the source data that supports this exaggeration/claim?
                """
                # (Throws an error if not supported by default)
                if not ground_truth.get("supports_qualitative_claims", False):
                    problems.append({
                        "type": "unsupported_qualitative_claim",
                        "detail": f"Unsupported qualitative assertion/invention found: '{found_phrase}'",
                        "claim": claim_text
                    })
        
        return problems

    def extract_numbers(self, text):
        # Extracts numbers and percentages (ex: '45%', '45', '90')
        if not text or not isinstance(text, str):
            return set()
        return set(re.findall(r'\b\d+(?:%\b|\b)', text.lower()))

    def verify_metrics(self, extracted_claims, record_outcomes):
        """
        Compares the metric claims with the outcomes in the source record
        Looks for the numerical values and words matchings and makes a verification
        """
        if not extracted_claims:
            return True

        if not record_outcomes or not isinstance(record_outcomes, list):
            record_outcomes = []

        outcome_texts = [o.get("metric", "").lower() for o in record_outcomes if isinstance(o, dict) and o.get("metric")]
        all_outcome_numbers = set()
        for ot in outcome_texts:
            all_outcome_numbers.update(self.extract_numbers(ot))

        for claim in extracted_claims:
            if not claim or not isinstance(claim, str):
                continue
                
            claim_lower = claim.lower()

            # 1. Is there a one-to-one or sub text matching?
            if any(claim_lower in outcome for outcome in outcome_texts):
                continue

            # 2. Flexible Matching (Number Control)
            claim_numbers = self.extract_numbers(claim_lower)
            if claim_numbers:
                # Are all the numbers in metric is inside the numbers in the source data?
                if claim_numbers.issubset(all_outcome_numbers):
                    continue # Numbers are matching, accepted!
                else:
                    return False # There is fake a number/percentage that is not in the record!

            # If there no numbers are included or no one-to-one matching suspicious metric
            return False

        return True
    
    def verify_client_naming(self, draft_text, record_client, may_be_named):
        """
        Checks the customer privacy rule
        If 'may_be_named' is False and the customer name is inside the draft returns False (breach)
        """
        if not record_client or not draft_text:
            return True

        if may_be_named:
            return True

        client_clean = str(record_client).strip().lower()
        draft_clean = str(draft_text).lower()

        if client_clean in draft_clean:
            return False
        
        return True

if __name__ == "__main__":
    checker = EntailmentChecker()
    print("✅ EntailmentChecker class is updated!")

"""
############### OLD VERSION ###################
class EntailmentChecker:
    def __init__(self):
        pass

    def verify_metrics(self, extracted_claims, record_outcomes):
        # Compares the metric claims with the outcomes
        # If all claims are in the record returns True, at least one of them is missing/wrong returns False
        if not extracted_claims:
            return True

        # Turns each metric text into lower case
        outcome_texts = [o.get("metric", "").lower() for o in record_outcomes if isinstance(o, dict)]
        
        for claim in extracted_claims:
            claim_lower = claim.lower()
            # Is the claim appears anywhere inside the metric
            match_found = any(claim_lower in outcome for outcome in outcome_texts)
            if not match_found:
                return False # There is a fake/false claim in the record!

        return True

    def verify_client_naming(self, draft_text, record_client, may_be_named):
        # Checks the customer privacy rules (may_be_named)
        # If 'may_be_named' is False and the customer name is inside the draft returns False (breach)
        if not record_client:
            return True

        if not may_be_named and record_client.lower() in draft_text.lower():
            return False # There is a privacy breach!

        return True

if __name__ == "__main__":
    checker = EntailmentChecker()
    print("✅ Entailment Checker class loaded successfuly and object created!")

"""