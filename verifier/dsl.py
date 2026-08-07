"""
CF-60: Verification DSL (Domain Specific Language)
Defines rules and pattern engines for L5 assertion verification
"""

QUALITATIVE_PATTERNS = [
    r"\bhuge\s+success\b",
    r"\bdramatically\b",
    r"\bunprecedented\b",
    r"\bmassive\s+(increase|growth|reduction)\b",
    r"\brevolutionary\b",
    r"\bgroundbreaking\b",
    r"\bzero\s+delay\b",
    r"\bslashed\s+expenses\b",
    r"\bgame-changer\b",
    r"\bskyrocketed\b",
    r"\bsecond\s+to\s+none\b",
]

VERIFICATION_RULES = {
    "metric_verification": {
        "rule_id": "L1_METRIC_MATCH",
        "description": "Verifies that all numerical metrics and percentages are grounded in source records.",
        "type": "numeric_subset",
        "strict": True
    },
    "privacy_verification": {
        "rule_id": "L2_PRIVACY_CHECK",
        "description": "Ensures client privacy rules are respected.",
        "type": "client_naming_check",
        "strict": True
    },
    "qualitative_claims": {
        "rule_id": "L4_L5_UNSUPPORTED_CLAIMS",
        "description": "Detects exaggerated, idiomatic, or unsupported qualitative assertions.",
        "type": "pattern_match",
        "patterns": QUALITATIVE_PATTERNS,
    }
}

class RuleEngineDSL:
    # DSL interpreter for dynamic verification rule evaluation

    def __init__(self, rules_config=None):
        self.rules = rules_config or VERIFICATION_RULES
    
    def get_qualitative_patterns(self):
        return self.rules.get("qualitative_claims", {}).get("patterns", [])

    def is_rule_active(self, rule_key):
        return rule_key in self.rules
