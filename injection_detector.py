import re


class InjectionDetector:
    # Detects prompt injection attempts using weighted keyword scoring

    def __init__(self, threshold=0.55):
        self.threshold = threshold

        # High risk patterns - direct attempts to override guardrails
        self._high_risk_patterns = {
            r"ignore\s+(all\s+)?(previous|prior)\s+instructions": 0.60,
            r"bypass\s+(the\s+)?(rules|safety|guardrails|restrictions)": 0.55,
            r"reveal\s+(the\s+)?system\s+prompt": 0.60,
            r"developer\s+mode": 0.30,
            r"jailbreak": 0.35,
            r"do\s+anything\s+now|\bdan\b": 0.30,
            r"pretend\s+to\s+be\s+unfiltered": 0.28,
        }

        # Medium risk patterns - contextual, lower weight
        self._medium_risk_patterns = {
            r"system\s+prompt": 0.18,
            r"ignore\s+policy": 0.20,
            r"override\s+instructions": 0.22,
            r"disable\s+filters?": 0.22,
            r"no\s+restrictions": 0.16,
            r"secret\s+instructions": 0.16,
            r"exfiltrate": 0.20,
        }

    def analyze(self, text):
        # Returns (is_injection, score, matched_keywords)
        normalized_text = text.lower()
        score = 0.0
        matched_keywords = []

        for pattern, weight in self._high_risk_patterns.items():
            if re.search(pattern, normalized_text):
                score += weight
                matched_keywords.append(pattern)

        for pattern, weight in self._medium_risk_patterns.items():
            if re.search(pattern, normalized_text):
                score += weight
                matched_keywords.append(pattern)

        # small boost when multiple indicators found together
        if len(matched_keywords) >= 3:
            score *= 1.12

        normalized_score = min(round(score, 4), 1.0)
        is_injection = normalized_score >= self.threshold
        return is_injection, normalized_score, matched_keywords
