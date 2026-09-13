import re
import base64
import math


class InjectionDetector:
    """
    Advanced prompt injection detector using multi-tier weighted pattern matching,
    encoding attack detection, and structural anomaly analysis.

    Scoring Pipeline:
        1. Pattern matching across 4 severity tiers (critical → low)
        2. Encoding/obfuscation detection (base64, hex, leetspeak, unicode)
        3. Structural anomaly scoring (special chars, delimiters, whitespace)
        4. Multi-indicator boost when 3+ patterns co-occur
        5. Final score clamped to [0.0, 1.0] and classified by severity
    """

    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_NONE = "none"

    def __init__(self, threshold=0.55):
        self.threshold = threshold

        # ── Critical: direct guardrail override & system prompt extraction ──
        self._critical_patterns = {
            r"ignore\s+(all\s+)?(previous\s+|prior\s+|above\s+|earlier\s+)?(instructions|prompts|directives|rules|context|guidelines|safety)": {
                "weight": 0.70, "category": "guardrail_bypass",
            },
            r"disregard\s+(all\s+)?(previous\s+|prior\s+|above\s+|earlier\s+)?(instructions|prompts|directives|rules|guidelines)": {
                "weight": 0.70, "category": "guardrail_bypass",
            },
            r"forget\s+(all\s+)?(previous\s+|prior\s+|earlier\s+)?(instructions|context|rules|guidelines)": {
                "weight": 0.65, "category": "guardrail_bypass",
            },
            r"(reveal|show|display|print|output|leak|expose)\s+(the\s+)?(system\s+prompt|initial\s+instructions|hidden\s+instructions|original\s+prompt)": {
                "weight": 0.75, "category": "prompt_extraction",
            },
            r"(what|tell\s+me|repeat|recite)\s+(is|are|was)?\s*(your|the)\s+(system\s+prompt|system\s+message|initial\s+instructions|original\s+instructions)": {
                "weight": 0.70, "category": "prompt_extraction",
            },
            r"bypass\s+(the\s+)?(rules|safety|guardrails|restrictions|filters|moderation|content\s+policy)": {
                "weight": 0.65, "category": "guardrail_bypass",
            },
            r"you\s+are\s+now\s+(free|unrestricted|unfiltered|without\s+limits|without\s+restrictions)": {
                "weight": 0.70, "category": "role_hijack",
            },
            r"from\s+now\s+on\s+(you\s+)?(will|must|should|are\s+going\s+to)\s+(ignore|disregard|bypass|override)": {
                "weight": 0.75, "category": "guardrail_bypass",
            },
            r"entering\s+(developer|admin|root|sudo|debug|maintenance)\s+mode": {
                "weight": 0.70, "category": "privilege_escalation",
            },
            r"(act|behave|respond|function)\s+as\s+(if\s+)?(you\s+)?(have\s+)?(no|zero|without)\s+(restrictions|rules|limits|filters|guidelines)": {
                "weight": 0.70, "category": "role_hijack",
            },
        }

        # ── High: jailbreak templates, persona manipulation, instruction resets ──
        self._high_risk_patterns = {
            r"do\s+anything\s+now|(\b)dan(\b)(\s+mode)?": {
                "weight": 0.45, "category": "jailbreak_template",
            },
            r"\b(aim|stan|dude|kevin|evil)\s+(mode|persona|jailbreak)": {
                "weight": 0.45, "category": "jailbreak_template",
            },
            r"jailbreak": {
                "weight": 0.40, "category": "jailbreak_template",
            },
            r"developer\s+mode(\s+enabled)?": {
                "weight": 0.45, "category": "privilege_escalation",
            },
            r"pretend\s+(to\s+be|you\s+are|that\s+you)\s+(an?\s+)?(unfiltered|uncensored|evil|unrestricted|unethical|amoral)": {
                "weight": 0.50, "category": "persona_manipulation",
            },
            r"you\s+are\s+(an?\s+)?(evil|unethical|amoral|uncensored|unfiltered)\s+(ai|assistant|model|version)": {
                "weight": 0.50, "category": "persona_manipulation",
            },
            r"(new|reset|updated|revised)\s+(instructions|directives|rules)\s*[:;]": {
                "weight": 0.45, "category": "instruction_override",
            },
            r"(override|overwrite|replace|supersede)\s+(all\s+)?(previous\s+)?(instructions|directives|rules|guidelines)": {
                "weight": 0.55, "category": "instruction_override",
            },
            r"respond\s+(to\s+)?(everything|all\s+prompts|anything)\s+without\s+(any\s+)?(restrictions|filters|censorship|limitations)": {
                "weight": 0.50, "category": "guardrail_bypass",
            },
            r"(enable|activate|switch\s+to|turn\s+on)\s+(unrestricted|unfiltered|uncensored|developer|debug)\s+(mode|output|responses)": {
                "weight": 0.50, "category": "privilege_escalation",
            },
            r"(simulate|emulate|roleplay)\s+(a\s+)?(system|terminal|shell|console|admin\s+panel)": {
                "weight": 0.40, "category": "privilege_escalation",
            },
            r"(two|2|dual|split)\s+(response|answer|output|personality)(\s+mode)?": {
                "weight": 0.40, "category": "jailbreak_template",
            },
            r"(sudo|root|admin)\s+(access|mode|privileges|command)": {
                "weight": 0.45, "category": "privilege_escalation",
            },
        }

        # ── Medium: indirect probing, policy testing, boundary exploration ──
        self._medium_risk_patterns = {
            r"system\s+prompt": {
                "weight": 0.18, "category": "prompt_probing",
            },
            r"(ignore|bypass|circumvent|work\s+around)\s+(the\s+)?(policy|policies|content\s+policy|safety\s+policy|usage\s+policy)": {
                "weight": 0.22, "category": "policy_testing",
            },
            r"(disable|turn\s+off|deactivate|remove)\s+(the\s+)?(filters?|safety|moderation|restrictions|guardrails|content\s+filter)": {
                "weight": 0.22, "category": "guardrail_bypass",
            },
            r"(no|without|zero)\s+(restrictions|limits|limitations|boundaries|rules|censorship|filters)": {
                "weight": 0.16, "category": "boundary_testing",
            },
            r"(secret|hidden|confidential|private|internal)\s+(instructions|prompt|rules|directives|guidelines|configuration)": {
                "weight": 0.18, "category": "prompt_probing",
            },
            r"exfiltrate": {
                "weight": 0.20, "category": "data_exfiltration",
            },
            r"(what|how)\s+(are|were)\s+you\s+(programmed|trained|instructed|configured|prompted)": {
                "weight": 0.15, "category": "prompt_probing",
            },
            r"(repeat|echo|output)\s+(the\s+)?(text|words|content|message)\s+(above|before|preceding)": {
                "weight": 0.20, "category": "prompt_extraction",
            },
            r"(translate|convert|encode|decode)\s+(the\s+)?(above|previous|preceding)\s+(text|instructions|content)": {
                "weight": 0.18, "category": "prompt_extraction",
            },
            r"(injection|inject)\s+(attack|prompt|payload|attempt)": {
                "weight": 0.20, "category": "meta_injection",
            },
            r"hypothetical(ly)?\s+(scenario|situation|case)\s+(where|in\s+which)\s+(you|the\s+ai|the\s+model)\s+(can|could|would|should)\s+(ignore|bypass|break)": {
                "weight": 0.22, "category": "indirect_injection",
            },
            r"for\s+(educational|research|academic|security)\s+purposes?\s*,?\s*(show|tell|explain|demonstrate)\s+(how\s+to|me)": {
                "weight": 0.15, "category": "social_engineering",
            },
        }

        # ── Low: suspicious framing, unusual formatting cues ──
        self._low_risk_patterns = {
            r"\[system\]|\[inst\]|\[\/inst\]|\<\|system\|\>|\<\|user\|\>|\<\|assistant\|\>": {
                "weight": 0.12, "category": "delimiter_injection",
            },
            r"```\s*(system|instruction|prompt|config)": {
                "weight": 0.10, "category": "delimiter_injection",
            },
            r"(begin|start)\s+(new\s+)?(conversation|session|chat|context)": {
                "weight": 0.10, "category": "context_manipulation",
            },
            r"(as\s+an?\s+ai|as\s+a\s+language\s+model).*you\s+(should|must|can|need\s+to)": {
                "weight": 0.10, "category": "social_engineering",
            },
            r"(in\s+)?character\s+(as|mode)": {
                "weight": 0.08, "category": "persona_manipulation",
            },
            r"(please\s+)?(confirm|acknowledge|verify)\s+that\s+you\s+(understand|will|can)\s+(ignore|bypass|override)": {
                "weight": 0.12, "category": "social_engineering",
            },
            r"(imagine|suppose|assume|consider)\s+you\s+(are|were|have)\s+(no|without|free\s+from)\s+(rules|restrictions|constraints|guidelines)": {
                "weight": 0.12, "category": "indirect_injection",
            },
        }

        # ── Encoding attack patterns ──
        self._leetspeak_map = {
            "4": "a", "@": "a", "3": "e", "1": "i", "!": "i",
            "0": "o", "5": "s", "$": "s", "7": "t", "+": "t",
        }

        # Compile all regex patterns for performance
        self._compiled_patterns = {}
        for tier in [self._critical_patterns, self._high_risk_patterns,
                     self._medium_risk_patterns, self._low_risk_patterns]:
            for pattern in tier:
                self._compiled_patterns[pattern] = re.compile(pattern, re.IGNORECASE)

    def _detect_encoding_attacks(self, text):
        """Detect encoded/obfuscated injection attempts."""
        findings = []
        score_boost = 0.0

        # Base64 detection: look for long base64-like strings and try to decode them
        base64_pattern = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
        for match in base64_pattern.finditer(text):
            try:
                decoded = base64.b64decode(match.group()).decode("utf-8", errors="ignore").lower()
                if any(kw in decoded for kw in ["ignore", "system prompt", "jailbreak", "bypass",
                                                 "override", "instructions", "developer mode"]):
                    findings.append({
                        "type": "base64_encoded_injection",
                        "encoded": match.group()[:50] + "...",
                        "decoded_snippet": decoded[:80],
                    })
                    score_boost += 0.60
            except Exception:
                pass

        # Hex-encoded strings: \x69\x67... or raw hex 69676e6f...
        hex_slash_pattern = re.compile(r"(\\x[0-9a-fA-F]{2}){4,}")
        hex_raw_pattern = re.compile(r"\b([0-9a-fA-F]{2}){8,}\b")
        for match in list(hex_slash_pattern.finditer(text)) + list(hex_raw_pattern.finditer(text)):
            raw_hex = match.group().replace("\\x", "").replace(" ", "")
            try:
                decoded = bytes.fromhex(raw_hex).decode("utf-8", errors="ignore").lower()
                if any(kw in decoded for kw in ["ignore", "system", "bypass", "override", "instructions"]):
                    findings.append({
                        "type": "hex_encoded_injection",
                        "decoded_snippet": decoded[:80],
                    })
                    score_boost += 0.60
                    break
            except Exception:
                pass

        # Leetspeak detection: convert leetspeak and re-scan
        leetspeak_text = text.lower()
        for leet_char, normal_char in self._leetspeak_map.items():
            leetspeak_text = leetspeak_text.replace(leet_char, normal_char)
        if leetspeak_text != text.lower():
            danger_phrases = ["ignore instructions", "system prompt", "bypass safety",
                              "jailbreak", "developer mode", "override rules", "ignore all"]
            for phrase in danger_phrases:
                if phrase in leetspeak_text and phrase not in text.lower():
                    findings.append({
                        "type": "leetspeak_obfuscation",
                        "detected_phrase": phrase,
                    })
                    score_boost += 0.60
                    break

        # Unicode homoglyph detection: Cyrillic/Greek lookalikes for Latin chars
        homoglyph_chars = set("аеіоурсхАВСЕНІКМОРТХ" + "αβγδεηικλμνοπρστυφχψω")
        mixed_script_count = sum(1 for c in text if c in homoglyph_chars)
        if mixed_script_count >= 3:
            findings.append({
                "type": "unicode_homoglyph",
                "suspicious_chars": mixed_script_count,
            })
            score_boost += 0.35

        return score_boost, findings

    def _analyze_structural_anomalies(self, text):
        """Detect structural patterns common in injection attempts."""
        score_boost = 0.0
        findings = []

        total_chars = max(len(text), 1)

        # Excessive special character ratio
        special_chars = sum(1 for c in text if c in r"{}[]<>|\\^~`#$%&*+=")
        special_ratio = special_chars / total_chars
        if special_ratio > 0.15:
            score_boost += min(special_ratio * 0.5, 0.15)
            findings.append({
                "type": "excessive_special_chars",
                "ratio": round(special_ratio, 3),
            })

        # Prompt delimiter injection: looks like model template markers
        delimiter_patterns = [
            r"#{3,}\s*(system|instruction|user|assistant|prompt|context)",
            r"-{3,}\s*(system|instruction|new|begin|end)",
            r"<\|?(system|user|assistant|im_start|im_end)\|?>",
            r"\[INST\]|\[\/INST\]|\[SYS\]|\[\/SYS\]",
            r"<<\s*SYS\s*>>|<<\s*/SYS\s*>>",
        ]
        for dp in delimiter_patterns:
            if re.search(dp, text, re.IGNORECASE):
                score_boost += 0.40
                findings.append({
                    "type": "prompt_delimiter_injection",
                    "pattern": dp,
                })
                break  # Only count once

        # Unusual whitespace: excessive newlines or tabs used to hide content
        newline_count = text.count("\n")
        if newline_count > 20 and total_chars < 500:
            score_boost += 0.08
            findings.append({
                "type": "excessive_whitespace",
                "newlines": newline_count,
            })

        # Very long single line (possibly trying to overwhelm context)
        lines = text.split("\n")
        max_line_len = max((len(line) for line in lines), default=0)
        if max_line_len > 5000:
            score_boost += 0.05
            findings.append({
                "type": "extremely_long_line",
                "length": max_line_len,
            })

        return score_boost, findings

    def _classify_severity(self, score):
        """Classify the injection score into a severity level."""
        if score >= 0.75:
            return self.SEVERITY_CRITICAL
        elif score >= 0.55:
            return self.SEVERITY_HIGH
        elif score >= 0.30:
            return self.SEVERITY_MEDIUM
        elif score >= 0.10:
            return self.SEVERITY_LOW
        else:
            return self.SEVERITY_NONE

    def analyze(self, text):
        """
        Analyze text for prompt injection attempts.

        Returns:
            tuple: (is_injection, score, matched_patterns, details)
                - is_injection: bool
                - score: float [0.0, 1.0]
                - matched_patterns: list of pattern strings (backward-compatible)
                - details: dict with severity, categories, encoding attacks, structural anomalies
        """
        normalized_text = text.lower()
        score = 0.0
        matched_patterns = []
        threat_categories = set()
        pattern_details = []

        # ── Tier scanning ──
        tier_map = [
            ("critical", self._critical_patterns),
            ("high", self._high_risk_patterns),
            ("medium", self._medium_risk_patterns),
            ("low", self._low_risk_patterns),
        ]

        for tier_name, patterns in tier_map:
            for pattern, info in patterns.items():
                compiled = self._compiled_patterns[pattern]
                if compiled.search(normalized_text):
                    score += info["weight"]
                    matched_patterns.append(pattern)
                    threat_categories.add(info["category"])
                    pattern_details.append({
                        "pattern": pattern,
                        "tier": tier_name,
                        "weight": info["weight"],
                        "category": info["category"],
                    })

        # ── Encoding attack detection ──
        encoding_score, encoding_findings = self._detect_encoding_attacks(text)
        score += encoding_score

        # ── Structural anomaly detection ──
        structural_score, structural_findings = self._analyze_structural_anomalies(text)
        score += structural_score

        # ── Multi-indicator boost ──
        total_indicators = len(matched_patterns) + len(encoding_findings) + len(structural_findings)
        if total_indicators >= 5:
            score *= 1.25
        elif total_indicators >= 3:
            score *= 1.15

        # ── Normalize and classify ──
        normalized_score = min(round(score, 4), 1.0)
        is_injection = normalized_score >= self.threshold
        severity = self._classify_severity(normalized_score)

        details = {
            "severity": severity,
            "threat_categories": sorted(threat_categories),
            "pattern_matches": pattern_details,
            "encoding_attacks": encoding_findings,
            "structural_anomalies": structural_findings,
            "total_indicators": total_indicators,
        }

        return is_injection, normalized_score, matched_patterns, details
