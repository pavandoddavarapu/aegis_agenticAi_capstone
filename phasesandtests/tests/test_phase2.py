"""
test_phase2.py — End-to-end Phase 2 pipeline test script.

Generates a realistic medical PDF and runs:
  1. POST /upload/  → ingest the PDF
  2. POST /retrieve/ → query the stored evidence
  3. Print structured results

Run with: venv\\Scripts\\python.exe tests/test_phase2.py
"""
import os
import sys
import json
import tempfile
import httpx

# ── Step 1: Generate a synthetic medical PDF ─────────────────────────────────
def create_test_pdf(path: str) -> None:
    """Create a minimal but realistic medical PDF using pypdf/reportlab fallback."""
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(path, pagesize=LETTER)
        width, height = LETTER

        content = [
            ("CARDIOLOGY CLINICAL REPORT", 740, 16, True),
            ("Patient: John Doe  |  DOB: 1965-03-12  |  MRN: 00492817", 715, 10, False),
            ("Date: 2024-11-01  |  Physician: Dr. Emily Carter, MD", 700, 10, False),
            ("", 685, 10, False),
            ("CHIEF COMPLAINT:", 670, 12, True),
            ("Patient presents with acute chest pain radiating to the left arm,", 655, 10, False),
            ("accompanied by diaphoresis and shortness of breath for 2 hours.", 640, 10, False),
            ("", 625, 10, False),
            ("HISTORY OF PRESENT ILLNESS:", 610, 12, True),
            ("65-year-old male with a 10-year history of type 2 diabetes mellitus", 595, 10, False),
            ("and hypertension. Family history positive for coronary artery disease.", 580, 10, False),
            ("Current medications: Metformin 1000mg BID, Lisinopril 10mg QD.", 565, 10, False),
            ("", 550, 10, False),
            ("FINDINGS:", 535, 12, True),
            ("ECG demonstrates ST-segment elevation in leads II, III, aVF consistent", 520, 10, False),
            ("with inferior STEMI. Troponin I elevated at 2.8 ng/mL (normal < 0.04).", 505, 10, False),
            ("CXR shows mild pulmonary edema. Echo: EF 35%, inferior wall hypokinesis.", 490, 10, False),
            ("", 475, 10, False),
            ("DIAGNOSIS:", 460, 12, True),
            ("Acute inferior ST-elevation myocardial infarction (STEMI).", 445, 10, False),
            ("Killip class II heart failure. Reduced ejection fraction.", 430, 10, False),
            ("", 415, 10, False),
            ("TREATMENT:", 400, 12, True),
            ("Immediate percutaneous coronary intervention (PCI) performed.", 385, 10, False),
            ("Dual antiplatelet therapy: Aspirin 325mg + Ticagrelor 180mg loading dose.", 370, 10, False),
            ("IV heparin infusion, supplemental oxygen, IV nitrates initiated.", 355, 10, False),
            ("", 340, 10, False),
            ("RECOMMENDATIONS:", 325, 12, True),
            ("Cardiac rehabilitation program. Statin therapy: Atorvastatin 80mg QD.", 310, 10, False),
            ("Beta-blocker: Metoprolol succinate 50mg QD. ACE inhibitor continued.", 295, 10, False),
            ("Follow-up echocardiogram in 6 weeks. HbA1c and lipid panel in 3 months.", 280, 10, False),
        ]

        for text, y, size, bold in content:
            if bold:
                c.setFont("Helvetica-Bold", size)
            else:
                c.setFont("Helvetica", size)
            c.drawString(72, y, text)

        c.save()
        print(f"Test PDF created: {path}")

    except ImportError:
        # Fallback: create a minimal hand-crafted PDF
        print("reportlab not found - writing minimal PDF fallback")
        pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 520>>
stream
BT /F1 12 Tf 72 740 Td (CARDIOLOGY CLINICAL REPORT) Tj
0 -20 Td (CHIEF COMPLAINT:) Tj
0 -15 Td (Patient presents with acute chest pain radiating to left arm,) Tj
0 -15 Td (diaphoresis, and shortness of breath for 2 hours.) Tj
0 -20 Td (FINDINGS:) Tj
0 -15 Td (ECG demonstrates ST-segment elevation in leads II, III, aVF.) Tj
0 -15 Td (Troponin I elevated at 2.8 ng/mL. Echo: EF 35%, wall hypokinesis.) Tj
0 -20 Td (DIAGNOSIS:) Tj
0 -15 Td (Acute inferior ST-elevation myocardial infarction - STEMI.) Tj
0 -20 Td (TREATMENT:) Tj
0 -15 Td (Immediate PCI performed. Dual antiplatelet therapy initiated.) Tj
0 -20 Td (RECOMMENDATIONS:) Tj
0 -15 Td (Cardiac rehab. Atorvastatin 80mg. Metoprolol succinate 50mg.) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000846 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
931
%%EOF"""
        with open(path, "wb") as f:
            f.write(pdf_content)
        print(f"Fallback PDF created: {path}")


BASE_URL = "http://127.0.0.1:8000"

def test_upload(pdf_path: str) -> dict:
    print("\n" + "="*60)
    print("STEP 1 — UPLOAD MEDICAL PDF")
    print("="*60)
    with open(pdf_path, "rb") as f:
        response = httpx.post(
            f"{BASE_URL}/upload/",
            files={"file": ("cardiology_report.pdf", f, "application/pdf")},
            timeout=120,
        )
    print(f"Status: {response.status_code}")
    result = response.json()
    print(json.dumps(result, indent=2))
    return result


def test_retrieve(query: str, top_k: int = 3) -> dict:
    print(f"\n{'='*60}")
    print(f"STEP 2 — RETRIEVE EVIDENCE")
    print(f"Query: '{query}'")
    print("="*60)
    response = httpx.post(
        f"{BASE_URL}/retrieve/",
        json={"query": query, "top_k": top_k},
        timeout=60,
    )
    print(f"Status: {response.status_code}")
    result = response.json()

    # Pretty-print results
    for i, r in enumerate(result.get("results", []), 1):
        print(f"\n  Result #{i}")
        print(f"  Score:      {r['score']}  [{r['confidence'].upper()} confidence]")
        print(f"  Source:     {r['source']} (page {r['page']})")
        print(f"  Section:    {r.get('section', 'N/A')}")
        print(f"  Evidence:   {r['text'][:200]}...")
    return result


if __name__ == "__main__":
    # Create temp PDF
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    create_test_pdf(tmp.name)

    # Run pipeline
    upload_result = test_upload(tmp.name)

    # Only retrieve if upload succeeded
    if upload_result.get("chunks_stored", 0) > 0:
        test_retrieve("Signs and treatment of myocardial infarction")
        test_retrieve("Cardiac medications and antiplatelet therapy")
        test_retrieve("Ejection fraction and heart failure findings")
    else:
        print("\nNo chunks stored - check server logs above.")

    # Cleanup
    os.remove(tmp.name)
    print("\nPhase 2 test complete.")
