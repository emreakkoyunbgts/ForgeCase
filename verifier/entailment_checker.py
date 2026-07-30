"""
CF-59: Entailment Checker Module
Validates claims extracted from drafts against ground-truth records
"""

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