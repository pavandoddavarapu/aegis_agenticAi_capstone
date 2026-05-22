"""
test_phase12_e2e.py — Phase 12 adaptive orchestration end-to-end integration test.

Tests the following scenario:
  1. Clinician submits a sparse query:
     "A patient complaining of sudden chest pain and shortness of breath."
  2. System detects clinical intent and missing critical information,
     and returns status="clarification_required" with clarification questions.
  3. Clinician answers the questions.
  4. System runs the full reasoning workflow using the answered context,
     returning the clinical intelligence report with evidence quality analysis.

Run with: venv\\Scripts\\python.exe tests/test_phase12_e2e.py
"""
import httpx
import json
import sys

# Reconfigure stdout/stderr for Windows UTF-8 console output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def run_test():
    print("=" * 70)
    print("PHASE 12 E2E TEST: CLARIFICATION LOOP & ADAPTIVE ORCHESTRATION")
    print("=" * 70)

    # ── Step 1: Health check ──────────────────────────────────────────────────
    try:
        r_root = httpx.get(f"{BASE_URL}/")
        print(f"✓ Connected to backend: {r_root.json().get('message')}")
        print(f"✓ Backend version: {r_root.json().get('phase')}\n")
    except Exception as e:
        print(f"❌ Failed to connect to backend at {BASE_URL}: {e}")
        sys.exit(1)

    # ── Step 2: Submit sparse query ───────────────────────────────────────────
    sparse_query = "A patient complaining of sudden chest pain and shortness of breath."
    print(f"STEP 1: Submitting sparse query...")
    print(f"Query: '{sparse_query}'")
    
    payload = {
        "query": sparse_query
    }
    
    response = httpx.post(f"{BASE_URL}/analyze/", json=payload, timeout=180)
    print(f"Response HTTP Code: {response.status_code}")
    res_data = response.json()
    
    status = res_data.get("status")
    print(f"Response Status: {status}")
    
    if status != "clarification_required":
        print(f"❌ Expected status 'clarification_required', but got '{status}'")
        print(json.dumps(res_data, indent=2))
        sys.exit(1)
        
    print("✓ Clarification loop triggered successfully!")
    print(f"Clinical Intent detected: {res_data.get('clinical_intent')}")
    
    questions = res_data.get("clarification_questions", [])
    print(f"Clarification Questions received ({len(questions)}):")
    for q in questions:
        print(f"  - [{q.get('priority').upper()}] {q.get('question_text')} (Hint: {q.get('hint', 'None')})")
        
    # ── Step 3: Answer clarification questions ──────────────────────────────
    print(f"\nSTEP 2: Answering clarification questions...")
    answers = {}
    for q in questions:
        q_text = q.get("question_text").lower()
        if "age" in q_text:
            answers["age"] = "65 years old"
        elif "vital" in q_text:
            answers["vitals_any"] = "BP 140/90, HR 95 bpm, SpO2 95%"
        elif "medication" in q_text:
            answers["medications"] = "Aspirin 75mg daily, Metformin 500mg daily"
        elif "history" in q_text:
            answers["past_history"] = "Hypertension, Type 2 Diabetes"
        else:
            # Fallback
            answers[q.get("question_id")] = "Not specified"

    print("Answers to submit:")
    for k, v in answers.items():
        print(f"  {k} => {v}")
        
    clarify_payload = {
        "query": sparse_query,
        "clarification_answers": answers
    }
    
    # ── Step 4: Submit answers ────────────────────────────────────────────────
    print(f"\nSTEP 3: Submitting answers to /analyze/clarify/ ...")
    response_clarified = httpx.post(f"{BASE_URL}/analyze/clarify/", json=clarify_payload, timeout=180)
    print(f"Response HTTP Code: {response_clarified.status_code}")
    
    res_data_clarified = response_clarified.json()
    status_clarified = res_data_clarified.get("status")
    print(f"Response Status: {status_clarified}")
    
    if status_clarified == "clarification_required":
        print("❌ Still got clarification required. Error!")
        print(json.dumps(res_data_clarified, indent=2))
        sys.exit(1)
        
    print("\n✓ Analysis completed successfully after clarification loop!")
    print(f"Confidence Label: {res_data_clarified.get('confidence_label')} ({res_data_clarified.get('confidence_score') * 100}%)")
    
    # Evidence quality
    eq = res_data_clarified.get("evidence_quality_summary") or {}
    print(f"Evidence Quality: {eq.get('overall_sufficiency', 'UNKNOWN').upper()} (Score: {eq.get('sufficiency_score')})")
    print(f"Sources Count: {eq.get('total_sources')} total, {eq.get('high_quality_count')} high quality, {eq.get('filtered_count')} filtered")
    
    # Contradictions
    cs = res_data_clarified.get("contradiction_summary") or {}
    print(f"Contradictions detected: {cs.get('has_contradictions')} (Severity: {cs.get('overall_severity')})")
    if cs.get("summary"):
        print(f"Contradiction Summary: {cs.get('summary')}")
        
    print("\nFinal Clinical Response Summary:")
    final_resp = res_data_clarified.get("final_response", "")
    print(final_resp[:500] + ("..." if len(final_resp) > 500 else ""))
    
    # Workflow Path
    print(f"\nAI Workflow Trace: {' -> '.join(res_data_clarified.get('workflow_trace', []))}")
    print("=" * 70)
    print("✓ PHASE 12 E2E TEST COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_test()
