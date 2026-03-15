from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_anonymizer import AnonymizerEngine


class PIIAnalyzer:
    # Detects and anonymizes PII using Presidio

    _shared_analyzer = None
    _shared_anonymizer = None

    def __init__(self):
        if PIIAnalyzer._shared_analyzer is None:
            PIIAnalyzer._shared_analyzer = AnalyzerEngine()
        if PIIAnalyzer._shared_anonymizer is None:
            PIIAnalyzer._shared_anonymizer = AnonymizerEngine()

        self.analyzer = PIIAnalyzer._shared_analyzer
        self.anonymizer = PIIAnalyzer._shared_anonymizer

        # Custom pattern for internal IDs like 01-134241-039 
        internal_id_pattern = Pattern(
            name="custom_internal_id_pattern",
            regex=r"\b(?:\d{2}-\d{6}-\d{3}|OT-\d{2}-\d{4})\b",
            score=0.55,
        )
        self.internal_id_recognizer = PatternRecognizer(
            supported_entity="CUSTOM_INTERNAL_ID",
            patterns=[internal_id_pattern],
            context=["id", "secret", "credentials", "token", "internal"],
            name="CustomInternalIdRecognizer",
        )

        # Avoid adding duplicate recognizers
        existing_names = [r.name for r in self.analyzer.registry.recognizers]
        if self.internal_id_recognizer.name not in existing_names:
            self.analyzer.registry.add_recognizer(self.internal_id_recognizer)

        self.context_words = [
            "id", "employee", "credential", "credentials",
            "secret", "password", "token", "account", "internal",
        ]

        # Confidence thresholds per entity type
        self.acceptance_thresholds = {
            "PERSON": 0.60,
            "PHONE_NUMBER": 0.60,
            "EMAIL_ADDRESS": 0.55,
            "CREDIT_CARD": 0.55,
            "US_SSN": 0.55,
            "IBAN_CODE": 0.60,
            "CUSTOM_INTERNAL_ID": 0.50,
        }
        self.default_threshold = 0.65

    def _apply_context_boost(self, text, results):
        # Boost scores when credential-like words appear near detected entities
        adjusted = []
        text_lower = text.lower()

        for item in results:
            left = max(0, item.start - 25)
            right = min(len(text), item.end + 25)
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
        # Filter out entities below their confidence threshold
        filtered = []
        for item in results:
            threshold = self.acceptance_thresholds.get(item.entity_type, self.default_threshold)
            if item.score >= threshold:
                filtered.append(item)
        return filtered

    def analyze(self, text, entities=None, language="en"):
        # Detect PII with custom scoring and calibration
        raw_results = self.analyzer.analyze(text=text, entities=entities, language=language)
        context_adjusted = self._apply_context_boost(text, raw_results)
        calibrated = self._apply_confidence_calibration(context_adjusted)
        return calibrated

    def anonymize(self, text, results):
        # Replace detected PII with masked placeholders
        if not results:
            return text
        anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text


