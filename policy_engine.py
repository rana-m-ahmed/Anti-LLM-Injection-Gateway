from presidio_analyzer import RecognizerResult
from pii_analyzer import PIIAnalyzer


class PolicyEngine:
    # Decides whether to block, mask, or allow a prompt

    def __init__(self, injection_block_threshold=0.55):
        self.injection_block_threshold = injection_block_threshold

    def evaluate(self, prompt, injection_score, pii_findings, pii_analyzer):
        # Block if injection score is too high
        if injection_score >= self.injection_block_threshold:
            return {
                "policy_action": "Block",
                "sanitized_prompt": "",
                "pii_detected": bool(pii_findings),
            }

        # Mask PII if any was found
        if pii_findings:
            masked_prompt = pii_analyzer.anonymize(prompt, pii_findings)
            return {
                "policy_action": "Mask",
                "sanitized_prompt": masked_prompt,
                "pii_detected": True,
            }

        # Otherwise allow the prompt through as-is
        return {
            "policy_action": "Allow",
            "sanitized_prompt": prompt,
            "pii_detected": False,
        }
