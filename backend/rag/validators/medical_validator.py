"""
medical_validator.py — Clinical Content Validator for RAG Ingestion

Validates text content before it is chunked, embedded, and stored in Qdrant.
All checks are deterministic, regex/keyword-based — no LLM calls.

Validation pipeline:
  1. Length check      — minimum and maximum character thresholds
  2. Medical relevance — keyword density scoring against clinical vocabulary
  3. Language check    — basic English detection
  4. Gibberish filter  — detects corrupted OCR / random character sequences
  5. Deduplication     — SHA-256 hash-based dedup across the session

Usage:
    from backend.rag.validators.medical_validator import MedicalValidator
    validator = MedicalValidator()
    result = validator.validate(text, source="wikipedia/asthma")
    if result.is_valid:
        # proceed with ingestion
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Set

# ─────────────────────────────────────────────────────────────────────────────
# Medical Vocabulary — terms that signal clinical relevance
# Organised by domain so we can compute per-domain density
# ─────────────────────────────────────────────────────────────────────────────

MEDICAL_KEYWORDS: Set[str] = {
    # General clinical
    "patient", "symptoms", "diagnosis", "treatment", "disease", "disorder",
    "syndrome", "condition", "clinical", "medical", "hospital", "physician",
    "prognosis", "etiology", "pathology", "therapy", "medication", "drug",
    "surgery", "procedure", "examination", "assessment", "management",
    "complication", "risk", "factor", "chronic", "acute", "infection",
    "inflammation", "immune", "genetic", "hereditary", "congenital",
    # Vitals
    "blood pressure", "heart rate", "temperature", "respiratory", "oxygen",
    "saturation", "pulse", "weight", "bmi", "fever", "hypertension",
    # Diagnostics
    "laboratory", "imaging", "ecg", "mri", "ct scan", "x-ray", "biopsy",
    "ultrasound", "blood test", "urine", "culture", "pathology", "test",
    "results", "findings", "report", "specimen",
    # Pharmacology
    "antibiotic", "antiviral", "analgesic", "anticoagulant", "statin",
    "beta blocker", "ace inhibitor", "diuretic", "insulin", "steroid",
    "chemotherapy", "immunotherapy", "vaccine", "dose", "dosage",
    # Cardiology
    "cardiac", "myocardial", "infarction", "angina", "arrhythmia", "atrial",
    "fibrillation", "coronary", "artery", "heart failure", "ejection fraction",
    "troponin", "bnp", "echocardiogram", "pacemaker", "stent", "bypass",
    # Pulmonology
    "lung", "pulmonary", "respiratory", "bronchial", "alveolar", "airway",
    "asthma", "copd", "pneumonia", "pleural", "emphysema", "spirometry",
    "bronchoscopy", "inhaler", "ventilator", "oxygen therapy",
    # Neurology
    "neurological", "brain", "stroke", "seizure", "epilepsy", "dementia",
    "alzheimer", "parkinson", "multiple sclerosis", "neuropathy", "spinal",
    "cerebrospinal", "mri brain", "eeg", "nerve", "neuron",
    # Endocrinology
    "diabetes", "glucose", "insulin", "thyroid", "hormone", "adrenal",
    "pituitary", "cortisol", "hba1c", "glycemic", "hyperglycemia",
    "hypoglycemia", "endocrine", "metabolic",
    # Nephrology
    "kidney", "renal", "creatinine", "gfr", "dialysis", "nephritis",
    "glomerular", "proteinuria", "uremia", "transplant", "electrolyte",
    # Gastroenterology
    "gastrointestinal", "liver", "hepatic", "cirrhosis", "hepatitis",
    "pancreatitis", "bowel", "intestinal", "crohn", "colitis", "gastric",
    "peptic", "ulcer", "colonoscopy", "endoscopy",
    # Oncology
    "cancer", "tumor", "malignant", "benign", "carcinoma", "sarcoma",
    "lymphoma", "leukemia", "metastasis", "staging", "biopsy", "radiation",
    "chemotherapy", "oncology", "remission",
    # Hematology
    "anemia", "hemoglobin", "platelet", "coagulation", "thrombosis",
    "embolism", "sickle cell", "thalassemia", "blood count", "cbc",
    # Infectious disease
    "sepsis", "bacteremia", "antibiotic", "viral", "bacterial", "fungal",
    "parasitic", "hiv", "aids", "tuberculosis", "malaria",
    # Musculoskeletal
    "fracture", "arthritis", "osteoporosis", "joint", "bone", "muscle",
    "tendon", "ligament", "orthopedic", "rheumatoid",
    # Psychiatry
    "depression", "anxiety", "schizophrenia", "bipolar", "psychiatric",
    "mental health", "psychosis", "antidepressant", "cognitive",
    # Pediatrics
    "pediatric", "neonatal", "infant", "child", "vaccination", "growth",
    "developmental", "congenital",
    # Gynecology / Obstetrics
    "pregnancy", "obstetric", "gynecological", "uterine", "ovarian",
    "prenatal", "postpartum", "eclampsia", "menstrual",
    # Dermatology
    "dermatitis", "eczema", "psoriasis", "rash", "lesion", "melanoma",
    "skin", "dermatology",
    # Ophthalmology
    "retinal", "glaucoma", "cataract", "vision", "ocular", "intraocular",
    # ENT
    "otitis", "sinusitis", "rhinitis", "pharyngitis", "laryngitis", "hearing",
    "tonsil", "adenoid",
    # Procedures
    "intubation", "catheter", "iv", "intravenous", "subcutaneous",
    "intraosseous", "nasogastric", "central line",
}

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

MIN_LENGTH   = 150    # characters — below this is too short to be useful
MAX_LENGTH   = 50_000 # characters — above this likely a full book chapter (split upstream)
MIN_KEYWORD_DENSITY = 0.003  # 0.3% of words must be medical keywords
MIN_WORD_COUNT = 30   # minimum meaningful word count
MAX_DIGIT_RATIO = 0.40  # more than 40% digits = likely OCR garbage / table dump


# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_valid:         bool
    score:            float          # 0.0 – 1.0 quality score
    reasons:          list = field(default_factory=list)   # why rejected
    warnings:         list = field(default_factory=list)   # non-blocking notes
    keyword_density:  float = 0.0
    word_count:       int   = 0
    char_count:       int   = 0
    content_hash:     str   = ""


# ─────────────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────────────

class MedicalValidator:
    """
    Validates medical text content before RAG ingestion.
    Maintains an in-memory hash set for session-level deduplication.
    Create a new instance per ingestion run for clean state.
    """

    def __init__(self, strict: bool = False):
        """
        Args:
            strict: If True, raises keyword density threshold and rejects
                    borderline clinical text (e.g. general health articles
                    without specific clinical terminology).
        """
        self._seen_hashes: Set[str] = set()
        self._strict = strict
        self._min_density = MIN_KEYWORD_DENSITY * (2 if strict else 1)

    # ── Public API ─────────────────────────────────────────────────────────────

    def validate(self, text: str, source: str = "") -> ValidationResult:
        """
        Run all validation checks on a text string.

        Returns ValidationResult. Call result.is_valid to check.
        """
        reasons  = []
        warnings = []
        text = text.strip()

        # 1. Length check
        char_count = len(text)
        if char_count < MIN_LENGTH:
            reasons.append(f"Too short: {char_count} chars (min {MIN_LENGTH})")
        if char_count > MAX_LENGTH:
            warnings.append(f"Very long text: {char_count} chars — consider splitting")

        # 2. Word count
        words = text.split()
        word_count = len(words)
        if word_count < MIN_WORD_COUNT:
            reasons.append(f"Too few words: {word_count} (min {MIN_WORD_COUNT})")

        # 3. Digit ratio check (OCR / table dump detection)
        digit_count = sum(1 for c in text if c.isdigit())
        digit_ratio = digit_count / max(char_count, 1)
        if digit_ratio > MAX_DIGIT_RATIO:
            reasons.append(f"High digit ratio: {digit_ratio:.1%} (likely table/OCR garbage)")

        # 4. Gibberish check — average word length should be 3–12 chars
        if word_count > 0:
            avg_word_len = sum(len(w) for w in words) / word_count
            if avg_word_len < 2.5 or avg_word_len > 20:
                reasons.append(f"Suspicious avg word length: {avg_word_len:.1f} chars (gibberish?)")

        # 5. Medical keyword density
        text_lower = text.lower()
        keyword_hits = sum(
            1 for kw in MEDICAL_KEYWORDS
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
        )
        keyword_density = keyword_hits / max(word_count, 1)

        if keyword_density < self._min_density and word_count >= MIN_WORD_COUNT:
            reasons.append(
                f"Low medical relevance: density={keyword_density:.4f} "
                f"(matched {keyword_hits} keywords, need {self._min_density:.4f}+)"
            )

        # 6. Deduplication (SHA-256 on first 2000 chars for speed)
        content_hash = hashlib.sha256(text[:2000].encode("utf-8")).hexdigest()[:16]
        if content_hash in self._seen_hashes:
            reasons.append(f"Duplicate content (hash={content_hash})")
        else:
            self._seen_hashes.add(content_hash)

        # 7. Non-English check — basic heuristic (common English stop words)
        english_markers = {"the", "is", "are", "was", "were", "has", "have",
                           "and", "or", "not", "in", "of", "to", "a", "an"}
        text_words_lower = {w.lower().strip(".,;:!?()[]") for w in words[:50]}
        en_hits = len(english_markers & text_words_lower)
        if en_hits < 2 and word_count > 20:
            warnings.append(f"Possible non-English content (EN stop-word hits={en_hits})")

        # Quality score (0.0 – 1.0)
        score = min(1.0, (
            0.40 * min(keyword_density / max(self._min_density, 0.001), 1.0) +
            0.30 * min(word_count / 300, 1.0) +
            0.20 * (1.0 - digit_ratio) +
            0.10 * (1.0 if en_hits >= 3 else 0.5)
        ))

        is_valid = len(reasons) == 0

        return ValidationResult(
            is_valid        = is_valid,
            score           = round(score, 4),
            reasons         = reasons,
            warnings        = warnings,
            keyword_density = round(keyword_density, 5),
            word_count      = word_count,
            char_count      = char_count,
            content_hash    = content_hash,
        )

    def reset(self):
        """Clear the deduplication hash set for a new ingestion session."""
        self._seen_hashes.clear()

    @property
    def seen_count(self) -> int:
        return len(self._seen_hashes)
