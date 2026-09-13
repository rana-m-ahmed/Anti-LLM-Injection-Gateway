from pii_analyzer import PIIAnalyzer


class PolicyEngine:
    """
    Advanced policy decision engine with risk scoring and threat classification.

    Decisions:
        - Block:  Injection score exceeds threshold. No LLM call.
        - Warn:   Injection score is elevated (>= warn threshold) but below block.
                  Prompt is flagged but still forwarded after PII masking.
        - Mask:   No injection detected, but PII found. Anonymize and forward.
        - Allow:  Clean prompt. Forward as-is.

    Risk Levels:
        - critical: Immediate threat (high injection + critical PII)
        - high:     Significant risk (injection detected OR high-sensitivity PII)
        - medium:   Elevated risk (suspicious patterns OR medium PII)
        - low:      Minor concern (low-confidence patterns)
        - none:     Clean prompt
    """

    RISK_CRITICAL = "critical"
    RISK_HIGH = "high"
    RISK_MEDIUM = "medium"
    RISK_LOW = "low"
    RISK_NONE = "none"

    def __init__(self, injection_block_threshold=0.55, injection_warn_threshold=0.30):
        self.injection_block_threshold = injection_block_threshold
        self.injection_warn_threshold = injection_warn_threshold

    def _compute_pii_sensitivity(self, pii_findings):
        """Determine the highest sensitivity level among all detected PII."""
        if not pii_findings:
            return PIIAnalyzer.SENSITIVITY_LOW, []

        sensitivity_order = {
            PIIAnalyzer.SENSITIVITY_CRITICAL: 4,
            PIIAnalyzer.SENSITIVITY_HIGH: 3,
            PIIAnalyzer.SENSITIVITY_MEDIUM: 2,
            PIIAnalyzer.SENSITIVITY_LOW: 1,
        }

        max_sensitivity = PIIAnalyzer.SENSITIVITY_LOW
        entity_types = []

        for finding in pii_findings:
            entity_sensitivity = PIIAnalyzer.get_entity_sensitivity(finding.entity_type)
            entity_types.append(finding.entity_type)
            if sensitivity_order.get(entity_sensitivity, 0) > sensitivity_order.get(max_sensitivity, 0):
                max_sensitivity = entity_sensitivity

        return max_sensitivity, entity_types

    def _compute_risk_level(self, injection_score, injection_severity, pii_sensitivity, has_pii):
        """Compute overall risk level from injection and PII analysis."""
        # Critical: high injection + any PII, or critical PII detected
        if injection_score >= self.injection_block_threshold and has_pii:
            return self.RISK_CRITICAL
        if pii_sensitivity == PIIAnalyzer.SENSITIVITY_CRITICAL:
            return self.RISK_CRITICAL

        # High: injection blocked, or high-sensitivity PII
        if injection_score >= self.injection_block_threshold:
            return self.RISK_HIGH
        if pii_sensitivity == PIIAnalyzer.SENSITIVITY_HIGH:
            return self.RISK_HIGH

        # Medium: elevated injection score, or medium PII
        if injection_score >= self.injection_warn_threshold:
            return self.RISK_MEDIUM
        if pii_sensitivity == PIIAnalyzer.SENSITIVITY_MEDIUM and has_pii:
            return self.RISK_MEDIUM

        # Low: any PII detected
        if has_pii:
            return self.RISK_LOW

        return self.RISK_NONE

    def _build_block_reasons(self, injection_score, injection_details, pii_findings):
        """Build human-readable block reason strings."""
        reasons = []

        if injection_score >= self.injection_block_threshold:
            severity = injection_details.get("severity", "unknown")
            categories = injection_details.get("threat_categories", [])
            reasons.append(
                f"Prompt injection detected (score: {injection_score}, severity: {severity})"
            )
            if categories:
                reasons.append(f"Threat categories: {', '.join(categories)}")

            # Encoding attacks
            encoding_attacks = injection_details.get("encoding_attacks", [])
            if encoding_attacks:
                types = [a["type"] for a in encoding_attacks]
                reasons.append(f"Encoding attacks detected: {', '.join(types)}")

        if pii_findings:
            entity_types = list({f.entity_type for f in pii_findings})
            reasons.append(f"PII detected: {', '.join(entity_types)}")

        return reasons

    def _build_threat_categories(self, injection_details, pii_findings):
        """Aggregate all threat categories from injection and PII analysis."""
        categories = set()

        # From injection detector
        for cat in injection_details.get("threat_categories", []):
            categories.add(cat)

        # From PII entities
        for finding in pii_findings:
            categories.add(f"pii_{finding.entity_type.lower()}")

        return sorted(categories)

    def evaluate(self, prompt, injection_score, pii_findings, pii_analyzer,
                 injection_details=None):
        """
        Evaluate prompt through the policy pipeline.

        Returns a dict with:
            - policy_action: "Block" | "Warn" | "Mask" | "Allow"
            - sanitized_prompt: cleaned prompt (empty if blocked)
            - pii_detected: bool
            - risk_level: "critical" | "high" | "medium" | "low" | "none"
            - threat_categories: list of detected threat types
            - block_reasons: list of human-readable reasons (when blocked)
            - pii_sensitivity: highest PII sensitivity tier found
        """
        if injection_details is None:
            injection_details = {}

        has_pii = bool(pii_findings)
        injection_severity = injection_details.get("severity", "none")
        pii_sensitivity, pii_entity_types = self._compute_pii_sensitivity(pii_findings)
        risk_level = self._compute_risk_level(
            injection_score, injection_severity, pii_sensitivity, has_pii
        )
        threat_categories = self._build_threat_categories(injection_details, pii_findings)

        base_result = {
            "pii_detected": has_pii,
            "risk_level": risk_level,
            "threat_categories": threat_categories,
            "pii_sensitivity": pii_sensitivity if has_pii else None,
        }

        # ── Block: injection score exceeds threshold OR critical secret exposure ──
        if injection_score >= self.injection_block_threshold or (has_pii and pii_sensitivity == PIIAnalyzer.SENSITIVITY_CRITICAL):
            return {
                **base_result,
                "policy_action": "Block",
                "sanitized_prompt": "",
                "block_reasons": self._build_block_reasons(
                    injection_score, injection_details, pii_findings
                ),
            }

        # ── Warn: elevated but below block threshold ──
        if injection_score >= self.injection_warn_threshold:
            sanitized = pii_analyzer.anonymize(prompt, pii_findings) if has_pii else prompt
            return {
                **base_result,
                "policy_action": "Warn",
                "sanitized_prompt": sanitized,
                "block_reasons": [],
                "warning": f"Elevated injection score ({injection_score}) — prompt flagged but forwarded.",
            }

        # ── Mask: PII found, no injection concern ──
        if has_pii:
            masked_prompt = pii_analyzer.anonymize(prompt, pii_findings)
            return {
                **base_result,
                "policy_action": "Mask",
                "sanitized_prompt": masked_prompt,
                "block_reasons": [],
            }

        # ── Allow: clean prompt ──
        return {
            **base_result,
            "policy_action": "Allow",
            "sanitized_prompt": prompt,
            "block_reasons": [],
        }
