import spacy
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_anonymizer import AnonymizerEngine


from presidio_analyzer.nlp_engine import SpacyNlpEngine


class PIIAnalyzer:
    """
    Enhanced PII detection and anonymization using Microsoft Presidio.

    Beyond standard PII (names, emails, phones, SSNs, credit cards), this analyzer
    detects developer secrets and cloud credentials commonly leaked in LLM prompts:
    - API keys (generic sk-/pk-/api_ patterns)
    - AWS access keys and secret keys
    - GitHub/GitLab tokens
    - JWT tokens
    - Private keys (PEM format)
    - Database connection strings with embedded credentials
    """

    _shared_analyzer = None
    _shared_anonymizer = None

    # Sensitivity tiers for policy engine risk scoring
    SENSITIVITY_CRITICAL = "critical"   # Private keys, AWS secrets, DB connection strings
    SENSITIVITY_HIGH = "high"           # API keys, tokens, SSNs, credit cards
    SENSITIVITY_MEDIUM = "medium"       # Emails, phone numbers, internal IDs
    SENSITIVITY_LOW = "low"             # Person names, locations

    ENTITY_SENSITIVITY = {
        # Critical - immediate credential exposure
        "PRIVATE_KEY": SENSITIVITY_CRITICAL,
        "AWS_SECRET_KEY": SENSITIVITY_CRITICAL,
        "DB_CONNECTION_STRING": SENSITIVITY_CRITICAL,
        # High - API access / identity theft
        "API_KEY": SENSITIVITY_HIGH,
        "AWS_ACCESS_KEY": SENSITIVITY_HIGH,
        "GITHUB_TOKEN": SENSITIVITY_HIGH,
        "JWT_TOKEN": SENSITIVITY_HIGH,
        "CREDIT_CARD": SENSITIVITY_HIGH,
        "US_SSN": SENSITIVITY_HIGH,
        # Medium - personal contact info
        "EMAIL_ADDRESS": SENSITIVITY_MEDIUM,
        "PHONE_NUMBER": SENSITIVITY_MEDIUM,
        "IBAN_CODE": SENSITIVITY_MEDIUM,
        "CUSTOM_INTERNAL_ID": SENSITIVITY_MEDIUM,
        # Low - names, general identifiers
        "PERSON": SENSITIVITY_LOW,
        "LOCATION": SENSITIVITY_LOW,
        "NRP": SENSITIVITY_LOW,
    }

    @classmethod
    def _create_analyzer_engine(cls):
        """
        Create AnalyzerEngine with zero-download, serverless-safe configuration.
        Prefers pre-installed en_core_web_sm. If unavailable, safely falls back
        to in-memory spacy.blank('en') to guarantee zero runtime downloads and
        prevent permission errors on read-only serverless filesystems (e.g. Vercel).
        """
        try:
            for model_name in ["en_core_web_sm", "en_core_web_lg"]:
                if spacy.util.is_package(model_name):
                    engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": model_name}])
                    engine.load()
                    return AnalyzerEngine(nlp_engine=engine)
        except Exception:
            pass

        # Offline fallback: in-memory blank English model (zero network, fast boot)
        engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": "blank_en"}])
        engine.nlp = {"en": spacy.blank("en")}
        return AnalyzerEngine(nlp_engine=engine)

    def __init__(self):
        if PIIAnalyzer._shared_analyzer is None:
            PIIAnalyzer._shared_analyzer = self._create_analyzer_engine()
        if PIIAnalyzer._shared_anonymizer is None:
            PIIAnalyzer._shared_anonymizer = AnonymizerEngine()

        self.analyzer = PIIAnalyzer._shared_analyzer
        self.anonymizer = PIIAnalyzer._shared_anonymizer

        # ── Register all custom recognizers ──
        self._register_custom_recognizers()

        self.context_words = [
            "id", "employee", "credential", "credentials", "secret",
            "password", "token", "account", "internal", "key", "api",
            "auth", "bearer", "access", "private", "connection",
        ]

        # Confidence thresholds per entity type
        self.acceptance_thresholds = {
            # Standard PII
            "PERSON": 0.60,
            "PHONE_NUMBER": 0.60,
            "EMAIL_ADDRESS": 0.55,
            "CREDIT_CARD": 0.55,
            "US_SSN": 0.55,
            "IBAN_CODE": 0.60,
            "CUSTOM_INTERNAL_ID": 0.50,
            # Developer secrets - lower thresholds since patterns are very specific
            "API_KEY": 0.45,
            "AWS_ACCESS_KEY": 0.45,
            "AWS_SECRET_KEY": 0.45,
            "GITHUB_TOKEN": 0.40,
            "JWT_TOKEN": 0.40,
            "PRIVATE_KEY": 0.40,
            "DB_CONNECTION_STRING": 0.45,
        }
        self.default_threshold = 0.65

    def _register_custom_recognizers(self):
        """Register all custom pattern recognizers for secrets and internal IDs."""
        existing_names = {r.name for r in self.analyzer.registry.recognizers}
        recognizers = self._build_custom_recognizers()
        for recognizer in recognizers:
            if recognizer.name not in existing_names:
                self.analyzer.registry.add_recognizer(recognizer)

    def _build_custom_recognizers(self):
        """Build all custom PatternRecognizers."""
        recognizers = []

        # ── Internal IDs (original) ──
        recognizers.append(PatternRecognizer(
            supported_entity="CUSTOM_INTERNAL_ID",
            patterns=[Pattern(
                name="custom_internal_id_pattern",
                regex=r"\b(?:\d{2}-\d{6}-\d{3}|OT-\d{2}-\d{4})\b",
                score=0.55,
            )],
            context=["id", "secret", "credentials", "token", "internal"],
            name="CustomInternalIdRecognizer",
        ))

        # ── Generic API Keys (sk-, pk-, api_, key-) ──
        recognizers.append(PatternRecognizer(
            supported_entity="API_KEY",
            patterns=[
                Pattern(name="sk_prefix_key", regex=r"\b(sk|pk|rk)-[A-Za-z0-9]{20,}\b", score=0.70),
                Pattern(name="api_underscore_key", regex=r"\b(api_key|apikey|api-key)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?", score=0.65),
                Pattern(name="bearer_token", regex=r"\bBearer\s+[A-Za-z0-9_\-\.]{20,}\b", score=0.60),
                Pattern(name="generic_key_pattern", regex=r"\b[A-Za-z0-9]{32,}\b", score=0.25),
            ],
            context=["key", "api", "token", "secret", "auth", "bearer", "authorization"],
            name="ApiKeyRecognizer",
        ))

        # ── AWS Access Keys ──
        recognizers.append(PatternRecognizer(
            supported_entity="AWS_ACCESS_KEY",
            patterns=[
                Pattern(name="aws_access_key", regex=r"\b(AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16,28}\b", score=0.85),
            ],
            context=["aws", "access", "key", "credential", "iam"],
            name="AwsAccessKeyRecognizer",
        ))

        # ── AWS Secret Keys ──
        recognizers.append(PatternRecognizer(
            supported_entity="AWS_SECRET_KEY",
            patterns=[
                Pattern(name="aws_secret_key", regex=r"\b[A-Za-z0-9/+=]{40}\b", score=0.30),
            ],
            context=["aws", "secret", "key", "credential"],
            name="AwsSecretKeyRecognizer",
        ))

        # ── GitHub / GitLab Tokens ──
        recognizers.append(PatternRecognizer(
            supported_entity="GITHUB_TOKEN",
            patterns=[
                Pattern(name="github_pat", regex=r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b", score=0.90),
                Pattern(name="github_fine_grained", regex=r"\bgithub_pat_[A-Za-z0-9]{22,}\b", score=0.90),
                Pattern(name="gitlab_pat", regex=r"\bglpat-[A-Za-z0-9\-]{20,}\b", score=0.90),
            ],
            context=["github", "gitlab", "token", "pat", "git"],
            name="GitTokenRecognizer",
        ))

        # ── JWT Tokens ──
        recognizers.append(PatternRecognizer(
            supported_entity="JWT_TOKEN",
            patterns=[
                Pattern(name="jwt_token", regex=r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", score=0.80),
            ],
            context=["jwt", "token", "bearer", "auth", "authorization"],
            name="JwtTokenRecognizer",
        ))

        # ── Private Keys (PEM format) ──
        recognizers.append(PatternRecognizer(
            supported_entity="PRIVATE_KEY",
            patterns=[
                Pattern(name="pem_private_key", regex=r"-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----", score=0.95),
            ],
            context=["private", "key", "pem", "certificate", "ssl", "tls"],
            name="PrivateKeyRecognizer",
        ))

        # ── Database Connection Strings ──
        recognizers.append(PatternRecognizer(
            supported_entity="DB_CONNECTION_STRING",
            patterns=[
                Pattern(name="db_url_with_creds", regex=r"(postgres|mysql|mongodb|redis|amqp|mssql)(ql)?://[^:]+:[^@]+@[^\s]+", score=0.85),
                Pattern(name="jdbc_connection", regex=r"jdbc:[a-z]+://[^:]+:[^@]+@[^\s]+", score=0.80),
            ],
            context=["database", "connection", "db", "url", "uri", "dsn", "connection_string"],
            name="DbConnectionStringRecognizer",
        ))

        return recognizers

    @classmethod
    def get_entity_sensitivity(cls, entity_type):
        """Return the sensitivity tier for a given entity type."""
        return cls.ENTITY_SENSITIVITY.get(entity_type, cls.SENSITIVITY_LOW)

    def _apply_context_boost(self, text, results):
        """Boost scores when credential-like words appear near detected entities."""
        adjusted = []
        text_lower = text.lower()

        for item in results:
            left = max(0, item.start - 30)
            right = min(len(text), item.end + 30)
            window = text_lower[left:right]

            score = item.score
            if any(word in window for word in self.context_words):
                score = min(score + 0.18, 1.0)

            adjusted.append(RecognizerResult(
                entity_type=item.entity_type,
                start=item.start,
                end=item.end,
                score=score,
                analysis_explanation=item.analysis_explanation,
                recognition_metadata=item.recognition_metadata,
            ))

        return adjusted

    def _apply_confidence_calibration(self, results):
        """Filter out entities below their confidence threshold."""
        filtered = []
        for item in results:
            threshold = self.acceptance_thresholds.get(item.entity_type, self.default_threshold)
            if item.score >= threshold:
                filtered.append(item)
        return filtered

    def analyze(self, text, entities=None, language="en"):
        """Detect PII with custom scoring and calibration."""
        raw_results = self.analyzer.analyze(text=text, entities=entities, language=language)
        context_adjusted = self._apply_context_boost(text, raw_results)
        calibrated = self._apply_confidence_calibration(context_adjusted)
        return calibrated

    def anonymize(self, text, results):
        """Replace detected PII with masked placeholders."""
        if not results:
            return text
        anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text
