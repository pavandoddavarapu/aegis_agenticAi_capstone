"""
ingest_lungs.py — Deep Lung & Respiratory Disease Knowledge Ingestion

Ingests comprehensive content about the lungs, airways, and all major
respiratory diseases from Wikipedia, MedlinePlus (NIH), and PubMed.

Topics Covered:
  - Lung anatomy & physiology
  - Obstructive: COPD, Asthma, Bronchiectasis, Cystic Fibrosis
  - Infectious: Pneumonia (CAP, HAP, VAP), TB, COVID-19, RSV, Influenza
  - Interstitial/Restrictive: IPF, ILD, Sarcoidosis, Hypersensitivity Pneumonitis
  - Vascular: Pulmonary Embolism, Pulmonary Hypertension, Cor Pulmonale
  - Pleural: Pleural Effusion, Pneumothorax, Empyema, Mesothelioma
  - Malignant: Lung Cancer (NSCLC/SCLC), Carcinoid
  - Critical Care: ARDS, Respiratory Failure, Mechanical Ventilation
  - Sleep: Obstructive Sleep Apnea, Central Sleep Apnea
  - Rare: LAM, PAP, Alpha-1 Antitrypsin, Silicosis, Asbestosis
  - Pediatric Lung: BPD, RDS, Croup, Bronchiolitis, CF

Usage:
    python scripts/ingest_lungs.py
    python scripts/ingest_lungs.py --pubmed-max 30
    python scripts/ingest_lungs.py --dry-run
    python scripts/ingest_lungs.py --pubmed-only
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict

# ─── Project root on path ──────────────────────────────────────────────────────
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.rag.ingestors.web_ingestor import (
    ingest_wikipedia, ingest_medlineplus, ingest_pubmed,
)
from backend.rag.validators.medical_validator import MedicalValidator
from backend.rag.chunker import chunk_pages
from backend.rag.embeddings import embed_texts
from backend.rag.qdrant_store import store_chunks, ensure_collection
from backend.rag.schemas import ExtractedPage, Chunk
from backend.utils.logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# LUNG KNOWLEDGE REGISTRY
# Organized by clinical category — each fetches from 3 sources:
#   wikipedia_articles  → full article text
#   medlineplus_queries → NIH consumer summaries
#   pubmed_queries      → recent clinical abstracts (20-30 per query)
# ─────────────────────────────────────────────────────────────────────────────

LUNG_DOMAINS: Dict[str, Dict] = {

    # ── 1. ANATOMY & PHYSIOLOGY ────────────────────────────────────────────
    "lung_anatomy_physiology": {
        "wikipedia_articles": [
            "Lung",
            "Human respiratory system",
            "Bronchus",
            "Alveolus",
            "Pleural cavity",
            "Diaphragm (anatomy)",
            "Pulmonary circulation",
            "Respiratory epithelium",
            "Surfactant (pulmonary)",
            "Dead space (physiology)",
            "Spirometry",
            "Ventilation-perfusion ratio",
            "Hypoxic pulmonary vasoconstriction",
            "Mucociliary clearance",
        ],
        "medlineplus_queries": [
            "how lungs work breathing respiratory system",
            "spirometry lung function test",
            "lung capacity volume measurement",
            "pulmonary function tests interpretation",
        ],
        "pubmed_queries": [
            "pulmonary physiology gas exchange oxygen carbon dioxide",
            "spirometry forced vital capacity FEV1 interpretation obstructive restrictive",
            "ventilation perfusion mismatch hypoxemia mechanism",
            "mucociliary clearance airway defense respiratory infection",
            "alveolar surfactant function respiratory distress",
            "diffusing capacity DLCO measurement pulmonary disease",
        ],
    },

    # ── 2. COPD ────────────────────────────────────────────────────────────
    "copd": {
        "wikipedia_articles": [
            "Chronic obstructive pulmonary disease",
            "Emphysema",
            "Chronic bronchitis",
            "Alpha-1 antitrypsin deficiency",
            "GOLD criteria",
            "Pulmonary rehabilitation",
        ],
        "medlineplus_queries": [
            "COPD chronic obstructive pulmonary disease symptoms treatment",
            "COPD exacerbation management hospitalization",
            "COPD inhaler bronchodilator LAMA LABA",
            "COPD oxygen therapy long term",
            "smoking cessation COPD prevention",
            "COPD pulmonary rehabilitation exercise",
        ],
        "pubmed_queries": [
            "COPD GOLD staging exacerbation risk management 2024",
            "COPD acute exacerbation systemic corticosteroid antibiotic",
            "COPD LAMA LABA dual bronchodilator therapy",
            "COPD triple therapy ICS LABA LAMA outcomes",
            "COPD non-invasive ventilation BiPAP acute exacerbation",
            "COPD oxygen therapy hypercapnia hypoxemia",
            "alpha-1 antitrypsin deficiency augmentation therapy emphysema",
            "COPD pulmonary rehabilitation exercise capacity quality of life",
            "COPD comorbidities cardiovascular depression anxiety",
            "COPD phenotypes emphysema chronic bronchitis overlap",
            "COPD roflumilast phosphodiesterase inhibitor exacerbation",
            "COPD end of life palliative care dyspnea management",
            "smoking cessation varenicline nicotine replacement COPD prevention",
        ],
    },

    # ── 3. ASTHMA ─────────────────────────────────────────────────────────
    "asthma": {
        "wikipedia_articles": [
            "Asthma",
            "Allergic asthma",
            "Exercise-induced bronchoconstriction",
            "Status asthmaticus",
            "Aspirin-exacerbated respiratory disease",
            "Eosinophilic asthma",
            "Occupational asthma",
        ],
        "medlineplus_queries": [
            "asthma symptoms triggers treatment inhaler",
            "asthma attack severe management emergency",
            "asthma biologic therapy dupilumab mepolizumab",
            "asthma control step-up step-down therapy",
            "childhood asthma diagnosis management",
        ],
        "pubmed_queries": [
            "severe asthma biologic therapy type 2 eosinophil IL-5 IL-4 IL-13",
            "asthma exacerbation emergency management systemic corticosteroid",
            "asthma GINA guidelines step therapy ICS LABA",
            "mepolizumab benralizumab dupilumab severe eosinophilic asthma",
            "asthma phenotype endotype T2 high T2 low",
            "asthma omalizumab IgE anti-allergic therapy",
            "occupational asthma workplace sensitizer exposure",
            "exercise induced bronchoconstriction diagnosis spirometry",
            "asthma COPD overlap syndrome ACO management",
            "status asthmaticus ICU intubation mechanical ventilation",
            "pediatric asthma diagnosis prevention management",
            "asthma fractional exhaled nitric oxide FeNO eosinophil",
        ],
    },

    # ── 4. PNEUMONIA ──────────────────────────────────────────────────────
    "pneumonia": {
        "wikipedia_articles": [
            "Pneumonia",
            "Community-acquired pneumonia",
            "Hospital-acquired pneumonia",
            "Ventilator-associated pneumonia",
            "Aspiration pneumonia",
            "Atypical pneumonia",
            "Pneumococcal pneumonia",
            "Legionella pneumophila",
            "Mycoplasma pneumonia",
            "Pneumocystis pneumonia",
            "Viral pneumonia",
        ],
        "medlineplus_queries": [
            "pneumonia symptoms treatment antibiotic",
            "community acquired pneumonia hospitalization",
            "pneumonia vaccine prevention elderly",
            "COVID-19 pneumonia treatment",
            "aspiration pneumonia risk factors prevention",
        ],
        "pubmed_queries": [
            "community acquired pneumonia CAP CURB-65 PSI severity antibiotic",
            "community acquired pneumonia beta-lactam macrolide fluoroquinolone",
            "hospital acquired pneumonia VAP antibiotic gram-negative coverage",
            "aspiration pneumonia anaerobic antibiotic management",
            "Legionella pneumonia fluoroquinolone azithromycin severity",
            "Pneumocystis jirovecii PCP HIV prophylaxis trimethoprim",
            "pneumococcal pneumonia bacteremia penicillin amoxicillin",
            "COVID-19 severe pneumonia dexamethasone remdesivir outcomes",
            "pneumonia biomarker procalcitonin CRP antibiotic stewardship",
            "pneumonia ICU mechanical ventilation outcomes mortality",
            "fungal pneumonia aspergillosis voriconazole immunocompromised",
            "pneumonia elderly nursing home atypical presentation",
            "rapid pneumonia diagnostic PCR multiplex panel antibiotic",
        ],
    },

    # ── 5. TUBERCULOSIS ───────────────────────────────────────────────────
    "tuberculosis": {
        "wikipedia_articles": [
            "Tuberculosis",
            "Mycobacterium tuberculosis",
            "Latent tuberculosis",
            "Multidrug-resistant tuberculosis",
            "Extensively drug-resistant tuberculosis",
            "Tuberculosis diagnosis",
            "BCG vaccine",
            "Miliary tuberculosis",
        ],
        "medlineplus_queries": [
            "tuberculosis TB symptoms diagnosis treatment",
            "latent TB infection isoniazid preventive therapy",
            "drug resistant TB MDR-TB treatment",
            "TB HIV co-infection management",
        ],
        "pubmed_queries": [
            "tuberculosis rifampicin isoniazid pyrazinamide ethambutol treatment",
            "latent tuberculosis IGRA TST isoniazid preventive therapy",
            "multidrug resistant tuberculosis MDR-TB bedaquiline pretomanid",
            "TB-HIV co-infection ART timing isoniazid preventive therapy",
            "drug resistant tuberculosis XDR-TB new regimen outcomes",
            "tuberculosis diagnosis GeneXpert Xpert MTB/RIF sputum smear",
            "extrapulmonary tuberculosis pleural meningeal miliary",
            "BCG vaccination tuberculosis prevention pediatric",
            "tuberculosis treatment monitoring hepatotoxicity adverse effects",
        ],
    },

    # ── 6. INTERSTITIAL LUNG DISEASE ─────────────────────────────────────
    "interstitial_lung_disease": {
        "wikipedia_articles": [
            "Pulmonary fibrosis",
            "Idiopathic pulmonary fibrosis",
            "Hypersensitivity pneumonitis",
            "Sarcoidosis",
            "Interstitial lung disease",
            "Nonspecific interstitial pneumonia",
            "Organizing pneumonia",
            "Lymphangioleiomyomatosis",
            "Pulmonary alveolar proteinosis",
            "Desquamative interstitial pneumonia",
            "Respiratory bronchiolitis-associated interstitial lung disease",
        ],
        "medlineplus_queries": [
            "pulmonary fibrosis symptoms diagnosis treatment",
            "sarcoidosis lung granuloma corticosteroid",
            "hypersensitivity pneumonitis bird breeder farmer lung",
            "interstitial lung disease breathing difficulty",
        ],
        "pubmed_queries": [
            "idiopathic pulmonary fibrosis IPF nintedanib pirfenidone antifibrotic",
            "IPF diagnosis high resolution CT honeycombing UIP pattern",
            "IPF acute exacerbation mortality outcomes",
            "sarcoidosis pulmonary diagnosis corticosteroid methotrexate",
            "hypersensitivity pneumonitis antigen exposure chronic fibrotic",
            "interstitial lung disease multidisciplinary diagnosis ATS ERS",
            "connective tissue disease ILD rheumatoid arthritis SSc management",
            "lymphangioleiomyomatosis LAM sirolimus mTOR",
            "pulmonary alveolar proteinosis whole lung lavage GM-CSF",
            "organizing pneumonia cryptogenic corticosteroid treatment",
            "ILD progressive fibrosing nintedanib antifibrotic",
            "lung transplant ILD IPF outcomes survival",
        ],
    },

    # ── 7. PULMONARY EMBOLISM & VASCULAR ─────────────────────────────────
    "pulmonary_vascular": {
        "wikipedia_articles": [
            "Pulmonary embolism",
            "Pulmonary hypertension",
            "Deep vein thrombosis",
            "Cor pulmonale",
            "Chronic thromboembolic pulmonary hypertension",
            "Pulmonary arteriovenous malformation",
            "Pulmonary vasculitis",
            "Venous thromboembolism",
        ],
        "medlineplus_queries": [
            "pulmonary embolism blood clot lung symptoms treatment",
            "pulmonary hypertension high blood pressure lungs",
            "deep vein thrombosis DVT anticoagulation",
            "blood thinners anticoagulation warfarin DOAC",
        ],
        "pubmed_queries": [
            "pulmonary embolism massive submassive thrombolysis anticoagulation",
            "pulmonary embolism DOAC rivaroxaban apixaban vs warfarin",
            "pulmonary embolism Wells score PERC rule diagnosis CT angiography",
            "pulmonary hypertension PAH WHO Group 1 treatment sildenafil bosentan",
            "chronic thromboembolic pulmonary hypertension CTEPH endarterectomy riociguat",
            "pulmonary embolism catheter directed thrombolysis CDT",
            "pulmonary embolism intermediate risk echo troponin management",
            "venous thromboembolism VTE prophylaxis surgery ICU heparin",
            "pulmonary embolism extended anticoagulation recurrence risk factor",
            "pulmonary arterial hypertension PAH combination therapy outcomes",
            "cor pulmonale right heart failure COPD echocardiography",
        ],
    },

    # ── 8. PLEURAL DISEASE ────────────────────────────────────────────────
    "pleural_disease": {
        "wikipedia_articles": [
            "Pleural effusion",
            "Pneumothorax",
            "Empyema",
            "Mesothelioma",
            "Pleuritis",
            "Chylothorax",
            "Hemothorax",
            "Tension pneumothorax",
        ],
        "medlineplus_queries": [
            "pleural effusion fluid around lungs diagnosis treatment",
            "pneumothorax collapsed lung treatment",
            "pleuritis pleurisy chest pain diagnosis",
            "mesothelioma asbestos lung cancer",
        ],
        "pubmed_queries": [
            "pleural effusion transudative exudative Light criteria diagnosis",
            "malignant pleural effusion indwelling pleural catheter talc pleurodesis",
            "spontaneous pneumothorax aspiration chest tube management",
            "tension pneumothorax needle decompression emergency",
            "empyema thoracis fibrinolytic intrapleural streptokinase DNase",
            "pleural effusion parapneumonic thoracocentesis antibiotic",
            "mesothelioma cisplatin pemetrexed immunotherapy checkpoint",
            "hemothorax thoracostomy drainage trauma management",
            "chylothorax octreotide thoracic duct ligation",
        ],
    },

    # ── 9. LUNG CANCER ────────────────────────────────────────────────────
    "lung_cancer": {
        "wikipedia_articles": [
            "Lung cancer",
            "Non-small-cell lung carcinoma",
            "Small-cell carcinoma",
            "Adenocarcinoma of the lung",
            "Squamous-cell lung carcinoma",
            "Pulmonary carcinoid tumour",
            "EGFR mutation in lung cancer",
            "ALK-positive lung cancer",
            "PD-L1 expression in lung cancer",
        ],
        "medlineplus_queries": [
            "lung cancer symptoms diagnosis staging",
            "lung cancer treatment chemotherapy immunotherapy",
            "lung cancer screening CT low dose",
            "non-small cell lung cancer targeted therapy",
            "small cell lung cancer chemotherapy",
        ],
        "pubmed_queries": [
            "non-small cell lung cancer NSCLC EGFR mutation osimertinib erlotinib gefitinib",
            "NSCLC ALK rearrangement crizotinib alectinib lorlatinib",
            "NSCLC PD-L1 pembrolizumab nivolumab atezolizumab immunotherapy",
            "small cell lung cancer SCLC extensive limited chemoradiotherapy",
            "lung cancer low dose CT screening NLST NELSON trial",
            "NSCLC ROS1 BRAF KRAS MET NTRK targeted therapy",
            "lung cancer stage III concurrent chemoradiation durvalumab",
            "lung cancer surgery lobectomy VATS RATS resection outcomes",
            "lung cancer brain metastases osimertinib alectinib CNS penetration",
            "lung cancer liquid biopsy circulating tumor DNA ctDNA",
            "NSCLC first line combination chemoimmunotherapy pembrolizumab",
            "lung cancer palliative care dyspnea symptom management",
            "lung cancer paraneoplastic syndrome SIADH Eaton Lambert",
            "lung cancer staging TNM mediastinoscopy EBUS PET-CT",
        ],
    },

    # ── 10. ARDS & CRITICAL CARE RESPIRATORY ─────────────────────────────
    "ards_critical_care": {
        "wikipedia_articles": [
            "Acute respiratory distress syndrome",
            "Respiratory failure",
            "Mechanical ventilation",
            "Positive end-expiratory pressure",
            "Extracorporeal membrane oxygenation",
            "Prone positioning",
            "High-flow nasal cannula",
            "Non-invasive ventilation",
            "Weaning from mechanical ventilation",
        ],
        "medlineplus_queries": [
            "ARDS acute respiratory distress syndrome treatment",
            "mechanical ventilation ICU respiratory failure",
            "ECMO heart lung bypass critical care",
            "COVID-19 ARDS mechanical ventilation",
        ],
        "pubmed_queries": [
            "ARDS lung protective ventilation low tidal volume ARMA trial",
            "ARDS prone positioning mortality 16 hours PROSEVA",
            "ARDS high PEEP recruitment maneuver oxygenation",
            "ARDS ECMO venovenous VV-ECMO EOLIA trial",
            "COVID-19 ARDS mechanical ventilation dexamethasone outcomes",
            "ARDS neuromuscular blocking cisatracurium ACURASYS",
            "ARDS conservative versus liberal fluid management FACTT",
            "ARDS definition Berlin criteria mild moderate severe",
            "weaning mechanical ventilation spontaneous breathing trial T-piece",
            "non-invasive ventilation NIV BiPAP acute hypercapnic failure",
            "high flow nasal cannula HFNC hypoxemic respiratory failure",
            "hypoxemic respiratory failure optiflow HFNC vs NIV",
            "ARDS biomarkers IL-6 IL-8 SP-D RAGE prognosis",
            "ICU sedation analgesia ABCDEF bundle ventilator",
            "ventilator induced lung injury VILI barotrauma volutrauma",
        ],
    },

    # ── 11. OBSTRUCTIVE SLEEP APNEA & SLEEP BREATHING ────────────────────
    "sleep_breathing": {
        "wikipedia_articles": [
            "Obstructive sleep apnea",
            "Central sleep apnea",
            "Sleep-disordered breathing",
            "Continuous positive airway pressure",
            "Obesity hypoventilation syndrome",
            "Upper airway resistance syndrome",
        ],
        "medlineplus_queries": [
            "sleep apnea symptoms CPAP treatment",
            "snoring sleep disordered breathing",
            "obesity hypoventilation sleep breathing",
            "CPAP therapy adherence sleep apnea",
        ],
        "pubmed_queries": [
            "obstructive sleep apnea OSA CPAP cardiovascular outcomes",
            "OSA diagnosis polysomnography home sleep test AHI",
            "CPAP therapy adherence adherence predictors outcomes",
            "OSA obesity hypoventilation syndrome treatment CPAP NIV",
            "central sleep apnea adaptive servo-ventilation ASV heart failure",
            "OSA surgical treatment uvulopalatopharyngoplasty mandibular",
            "OSA hypoglossal nerve stimulation upper airway surgery",
            "OSA atrial fibrillation hypertension cardiovascular comorbidity",
            "pediatric OSA adenotonsillectomy outcomes",
        ],
    },

    # ── 12. CYSTIC FIBROSIS ───────────────────────────────────────────────
    "cystic_fibrosis": {
        "wikipedia_articles": [
            "Cystic fibrosis",
            "CFTR protein",
            "Bronchiectasis",
            "Pseudomonas aeruginosa",
        ],
        "medlineplus_queries": [
            "cystic fibrosis symptoms lung treatment",
            "cystic fibrosis CFTR modulator ivacaftor",
            "bronchiectasis airways clearance physiotherapy",
        ],
        "pubmed_queries": [
            "cystic fibrosis CFTR modulator elexacaftor tezacaftor ivacaftor triple therapy",
            "cystic fibrosis Pseudomonas eradication tobramycin inhaled azithromycin",
            "cystic fibrosis pulmonary exacerbation IV antibiotic management",
            "cystic fibrosis airway clearance physiotherapy hypertonic saline dornase",
            "cystic fibrosis lung transplantation outcomes survival",
            "bronchiectasis exacerbation inhaled antibiotic long-term macrolide",
            "bronchiectasis airway clearance oscillating PEP physiotherapy",
            "bronchiectasis underlying etiology immunodeficiency NTM",
            "cystic fibrosis nutrition pancreatic enzyme replacement",
        ],
    },

    # ── 13. RARE LUNG DISEASES ────────────────────────────────────────────
    "rare_lung_diseases": {
        "wikipedia_articles": [
            "Lymphangioleiomyomatosis",
            "Pulmonary alveolar proteinosis",
            "Langerhans cell histiocytosis",
            "Alveolar microlithiasis",
            "Byssinosis",
            "Silicosis",
            "Asbestosis",
            "Coal workers' pneumoconiosis",
            "Berylliosis",
            "Pulmonary veno-occlusive disease",
        ],
        "medlineplus_queries": [
            "occupational lung disease silicosis asbestosis",
            "pneumoconiosis coal dust lung disease",
            "rare lung disease diagnosis treatment",
        ],
        "pubmed_queries": [
            "silicosis progressive massive fibrosis diagnosis management",
            "asbestosis mesothelioma risk asbestos exposure compensation",
            "lymphangioleiomyomatosis LAM mTOR sirolimus treatment",
            "pulmonary alveolar proteinosis whole lung lavage GM-CSF therapy",
            "Langerhans cell histiocytosis pulmonary smoking cessation cladribine",
            "occupational lung disease surveillance prevention management",
            "hypersensitivity pneumonitis antigen identification BAL lymphocytes",
        ],
    },

    # ── 14. INFECTIOUS RESPIRATORY (COVID, RSV, INFLUENZA) ───────────────
    "respiratory_infections": {
        "wikipedia_articles": [
            "COVID-19",
            "Influenza",
            "Respiratory syncytial virus",
            "Respiratory syncytial virus infection",
            "Hantavirus pulmonary syndrome",
            "Severe acute respiratory syndrome",
            "Middle East respiratory syndrome",
            "Coronavirus disease 2019",
            "Bronchiolitis",
            "Pertussis",
        ],
        "medlineplus_queries": [
            "COVID-19 respiratory infection symptoms treatment",
            "influenza flu antiviral oseltamivir treatment",
            "RSV respiratory syncytial virus infant adult",
            "respiratory infection antibiotic overuse stewardship",
        ],
        "pubmed_queries": [
            "COVID-19 dexamethasone baricitinib tocilizumab severe pneumonia",
            "COVID-19 antivirals nirmatrelvir paxlovid remdesivir molnupiravir",
            "COVID-19 long COVID post-acute sequelae pulmonary",
            "influenza severe infection oseltamivir baloxavir outcomes ICU",
            "RSV adult elderly hospitalization morbidity mortality",
            "RSV vaccine mRNA nirsevimab prevention adult infant",
            "respiratory syncytial virus bronchiolitis infant management",
            "hantavirus pulmonary syndrome HPS treatment supportive ECMO",
            "influenza pandemic preparedness antiviral stockpile",
            "respiratory coinfection viral bacterial pneumonia outcomes",
        ],
    },

    # ── 15. PEDIATRIC LUNG DISEASE ────────────────────────────────────────
    "pediatric_lung": {
        "wikipedia_articles": [
            "Respiratory distress syndrome (newborn)",
            "Bronchopulmonary dysplasia",
            "Croup",
            "Bronchiolitis",
            "Epiglottitis",
            "Tracheomalacia",
            "Congenital diaphragmatic hernia",
            "Persistent pulmonary hypertension of the newborn",
        ],
        "medlineplus_queries": [
            "neonatal respiratory distress syndrome surfactant",
            "croup stridor epinephrine dexamethasone",
            "RSV bronchiolitis infant treatment",
            "bronchopulmonary dysplasia premature lung",
        ],
        "pubmed_queries": [
            "neonatal RDS surfactant replacement therapy CPAP outcomes",
            "bronchopulmonary dysplasia BPD prevention caffeine dexamethasone",
            "pediatric croup dexamethasone nebulized epinephrine",
            "infant bronchiolitis RSV saline HFNC outcomes",
            "epiglottitis Haemophilus influenzae airway management",
            "congenital diaphragmatic hernia CDH ECMO management",
            "persistent pulmonary hypertension newborn iNO sildenafil",
            "childhood interstitial lung disease chILD classification",
            "pediatric asthma management inhaled corticosteroid step therapy",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Stats Tracking
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DomainStats:
    domain:         str
    pages_fetched:  int = 0
    pages_valid:    int = 0
    pages_rejected: int = 0
    chunks_created: int = 0
    chunks_stored:  int = 0
    errors:         List[str] = field(default_factory=list)


@dataclass
class IngestionSummary:
    domain_stats:   List[DomainStats] = field(default_factory=list)
    total_fetched:  int   = 0
    total_valid:    int   = 0
    total_rejected: int   = 0
    total_stored:   int   = 0
    elapsed_s:      float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Core Ingestion Logic (reused from ingest_medical_knowledge.py)
# ─────────────────────────────────────────────────────────────────────────────

def _ingest_pages(
    pages: List[ExtractedPage],
    validator: MedicalValidator,
    dry_run: bool,
    stats: DomainStats,
    source_description: str = "",
) -> None:
    """Validate → chunk → embed → store a list of ExtractedPages."""
    if not pages:
        return

    valid_pages: List[ExtractedPage] = []
    for page in pages:
        result = validator.validate(page.text, source=page.source)
        if result.is_valid:
            valid_pages.append(page)
            stats.pages_valid += 1
        else:
            stats.pages_rejected += 1
            logger.debug(
                f"[LungIngestor] REJECTED [{page.source} p{page.page}] "
                f"score={result.score} reasons={result.reasons}"
            )

    stats.pages_fetched += len(pages)

    if not valid_pages:
        return

    chunks = chunk_pages(valid_pages)
    stats.chunks_created += len(chunks)

    if dry_run or not chunks:
        logger.info(
            f"[LungIngestor] DRY-RUN | {source_description}: "
            f"{len(valid_pages)}/{len(pages)} valid → {len(chunks)} chunks (not stored)"
        )
        return

    # Embed in batches
    EMBED_BATCH = 64
    stored_total = 0
    for i in range(0, len(chunks), EMBED_BATCH):
        batch: List[Chunk] = chunks[i:i + EMBED_BATCH]
        texts = [c.text for c in batch]
        vectors = embed_texts(texts)
        if vectors:
            stored = store_chunks(batch, vectors)
            stored_total += stored

    stats.chunks_stored += stored_total
    logger.info(
        f"[LungIngestor] {source_description}: "
        f"{len(valid_pages)}/{len(pages)} valid → "
        f"{len(chunks)} chunks → {stored_total} stored"
    )


def ingest_lung_domain(
    domain_name: str,
    config: dict,
    validator: MedicalValidator,
    dry_run: bool = False,
    skip_wikipedia: bool = False,
    skip_medlineplus: bool = False,
    skip_pubmed: bool = False,
    pubmed_max: int = 25,
    request_delay: float = 0.5,
) -> DomainStats:
    """Run full ingestion pipeline for one lung domain."""
    stats = DomainStats(domain=domain_name)
    logger.info(f"\n{'='*60}")
    logger.info(f"[LungIngestor] Domain: {domain_name.upper()}")
    logger.info(f"{'='*60}")

    # ── Wikipedia ─────────────────────────────────────────────────────────
    if not skip_wikipedia:
        wiki_articles = config.get("wikipedia_articles", [])
        logger.info(f"[LungIngestor] Wikipedia: {len(wiki_articles)} articles")
        for title in wiki_articles:
            try:
                pages = ingest_wikipedia(title)
                _ingest_pages(pages, validator, dry_run, stats, f"wiki/{title}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"Wikipedia error for '{title}': {exc}"
                logger.error(f"[LungIngestor] {msg}")
                stats.errors.append(msg)

    # ── MedlinePlus ───────────────────────────────────────────────────────
    if not skip_medlineplus:
        ml_queries = config.get("medlineplus_queries", [])
        logger.info(f"[LungIngestor] MedlinePlus: {len(ml_queries)} queries")
        for query in ml_queries:
            try:
                pages = ingest_medlineplus(query)
                _ingest_pages(pages, validator, dry_run, stats, f"medlineplus/{query}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"MedlinePlus error for '{query}': {exc}"
                logger.error(f"[LungIngestor] {msg}")
                stats.errors.append(msg)

    # ── PubMed ────────────────────────────────────────────────────────────
    if not skip_pubmed:
        pm_queries = config.get("pubmed_queries", [])
        logger.info(f"[LungIngestor] PubMed: {len(pm_queries)} queries (max={pubmed_max} each)")
        for query in pm_queries:
            try:
                pages = ingest_pubmed(query, max_results=pubmed_max)
                _ingest_pages(pages, validator, dry_run, stats, f"pubmed/{query[:50]}")
                time.sleep(request_delay)
            except Exception as exc:
                msg = f"PubMed error for '{query}': {exc}"
                logger.error(f"[LungIngestor] {msg}")
                stats.errors.append(msg)

    logger.info(
        f"[LungIngestor] Domain '{domain_name}' complete: "
        f"fetched={stats.pages_fetched} valid={stats.pages_valid} "
        f"rejected={stats.pages_rejected} stored={stats.chunks_stored}"
    )
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest comprehensive lung & respiratory disease knowledge into Aegis RAG"
    )
    parser.add_argument(
        "--domains",
        type=str,
        default="",
        help=(
            "Comma-separated domain names to ingest (default: all). "
            f"Available: {', '.join(LUNG_DOMAINS.keys())}"
        ),
    )
    parser.add_argument("--dry-run",          action="store_true",
                        help="Validate and chunk but do NOT store to Qdrant")
    parser.add_argument("--skip-wikipedia",   action="store_true")
    parser.add_argument("--skip-medlineplus", action="store_true")
    parser.add_argument("--skip-pubmed",      action="store_true")
    parser.add_argument("--pubmed-only",      action="store_true",
                        help="Skip Wikipedia & MedlinePlus — only fetch PubMed abstracts")
    parser.add_argument("--pubmed-max",       type=int, default=25,
                        help="Max PubMed abstracts per query (default: 25)")
    parser.add_argument("--strict",           action="store_true",
                        help="Use strict medical content validation")
    parser.add_argument("--delay",            type=float, default=0.5,
                        help="Delay between web requests in seconds (default: 0.5)")
    args = parser.parse_args()

    # Resolve domains
    if args.domains:
        selected = [d.strip() for d in args.domains.split(",")]
        invalid  = [d for d in selected if d not in LUNG_DOMAINS]
        if invalid:
            print(f"ERROR: Unknown domains: {invalid}")
            print(f"Available: {list(LUNG_DOMAINS.keys())}")
            sys.exit(1)
        domains_to_run = {k: v for k, v in LUNG_DOMAINS.items() if k in selected}
    else:
        domains_to_run = LUNG_DOMAINS

    skip_wiki = args.skip_wikipedia or args.pubmed_only
    skip_ml   = args.skip_medlineplus or args.pubmed_only
    skip_pm   = args.skip_pubmed

    # Count total queries for estimate
    total_wiki = sum(len(v.get("wikipedia_articles", [])) for v in domains_to_run.values())
    total_ml   = sum(len(v.get("medlineplus_queries", [])) for v in domains_to_run.values())
    total_pm   = sum(len(v.get("pubmed_queries", [])) for v in domains_to_run.values())

    print(f"\n{'='*70}")
    print(f"  AEGIS LUNG & RESPIRATORY KNOWLEDGE INGESTION")
    print(f"  Domains  : {len(domains_to_run)}  ({', '.join(domains_to_run.keys())})")
    print(f"  Wikipedia: {'SKIP' if skip_wiki else f'{total_wiki} articles'}")
    print(f"  MedlinePlus: {'SKIP' if skip_ml else f'{total_ml} queries'}")
    print(f"  PubMed   : {'SKIP' if skip_pm else f'{total_pm} queries × {args.pubmed_max} abstracts'}")
    print(f"  Mode     : {'DRY-RUN (no storage)' if args.dry_run else 'LIVE (storing to Qdrant)'}")
    print(f"{'='*70}\n")

    if not args.dry_run:
        try:
            ensure_collection()
            logger.info("[LungIngestor] Qdrant collection ready.")
        except Exception as exc:
            print(f"ERROR: Cannot connect to Qdrant: {exc}")
            sys.exit(1)

    validator = MedicalValidator(strict=args.strict)
    summary   = IngestionSummary()
    start_t   = time.time()

    for domain_name, config in domains_to_run.items():
        stats = ingest_lung_domain(
            domain_name      = domain_name,
            config           = config,
            validator        = validator,
            dry_run          = args.dry_run,
            skip_wikipedia   = skip_wiki,
            skip_medlineplus = skip_ml,
            skip_pubmed      = skip_pm,
            pubmed_max       = args.pubmed_max,
            request_delay    = args.delay,
        )
        summary.domain_stats.append(stats)
        summary.total_fetched  += stats.pages_fetched
        summary.total_valid    += stats.pages_valid
        summary.total_rejected += stats.pages_rejected
        summary.total_stored   += stats.chunks_stored

    summary.elapsed_s = time.time() - start_t

    # ── Final Report ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  LUNG INGESTION COMPLETE — {summary.elapsed_s:.1f}s elapsed")
    print(f"{'='*70}")
    print(f"  {'Domain':<30} {'Fetched':>8} {'Valid':>7} {'Rejected':>9} {'Stored':>7}")
    print(f"  {'-'*65}")
    for ds in summary.domain_stats:
        print(
            f"  {ds.domain:<30} {ds.pages_fetched:>8} "
            f"{ds.pages_valid:>7} {ds.pages_rejected:>9} "
            f"{ds.chunks_stored:>7}"
        )
        if ds.errors:
            for err in ds.errors[:2]:
                print(f"    ⚠  {err[:80]}")
    print(f"  {'-'*65}")
    print(
        f"  {'TOTAL':<30} {summary.total_fetched:>8} "
        f"{summary.total_valid:>7} {summary.total_rejected:>9} "
        f"{summary.total_stored:>7}"
    )
    print(f"  Validator seen hashes: {validator.seen_count}")
    print(f"{'='*70}\n")
    print("  Next step: restart uvicorn or call the BM25 invalidate endpoint")
    print("  to rebuild the BM25 index with the new lung content.")

    return 0 if summary.total_stored > 0 or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
