# ⚕️ Aegis Clinical Intelligence Platform

<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-success.svg?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Next.js-14+-black.svg?style=for-the-badge&logo=next.js" alt="Next.js">
  <img src="https://img.shields.io/badge/FastAPI-0.109+-009688.svg?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Architecture-Multi--Agent-orange.svg?style=for-the-badge" alt="Multi-Agent">
</div>

<br />

Aegis is an enterprise-grade **Clinical Decision Support System (CDSS)** designed to act as an AI copilot for healthcare professionals. Built on a robust Multi-Agent System (MAS), Aegis combines deep semantic search, deterministic guardrails, and multimodal retrieval to provide safe, evidence-based diagnostic suggestions and treatment pathways. 

With a stunning, high-contrast "Medical White" UI, Aegis guarantees minimal cognitive load for clinicians while delivering maximum transparency into the AI's reasoning process.

---

## ✨ Key Features

- 🧠 **Multi-Agent Orchestration**: A hierarchical network of specialized AI agents handling complex reasoning, retrieval, validation, and reflection.
- 🩺 **Deterministic Guardrails**: Strict safety layers (Input, Output, Clinical, Prompt) ensuring HIPAA compliance, safe outputs, and strict prompt adherence.
- 🕸️ **GraphRAG & Multimodal Intake**: Deep semantic search across medical literature, integrating unstructured text, OCR from medical imaging (X-Rays, ECGs), and structured knowledge graphs.
- 🛡️ **Human-in-the-Loop (HITL)**: Confidence scoring and cross-source contradiction detection that instantly escalates critical decisions to human clinicians.
- ⚡ **Real-Time Telemetry Streaming**: Live streaming of the orchestration stages to the UI, giving clinicians complete transparency into the AI's "thought process."
- 🎨 **Medical White Aesthetic**: A clean, premium, accessible user interface designed specifically for clinical environments.

---

## 🏗️ Detailed Layered Architecture

Aegis enforces strict separation of concerns across 6 distinct architecture layers:

### 1. Presentation Layer (Frontend)
Built with **Next.js 14**, **React**, **Tailwind CSS**, and **Zustand**. 
- **`ConversationalChatPanel.tsx`**: Dynamic intent classification routes standard Q&A to a fast copilot, and complex patient data to the deep reasoning engine. Features a live execution trace viewer.
- **`GovernancePanel.tsx`**: Visualizes confidence scores, contradiction metrics, and data provenance.
- **`FileUploadZone.tsx`**: Drag-and-drop ingestion connected directly to the backend OCR pipeline.

### 2. API & Orchestration Layer (Backend)
Powered by **FastAPI** and **Uvicorn**. This layer manages highly concurrent REST API requests, websocket streaming for agent telemetry, and session context management.

### 3. Agentic Cognitive Layer (Multi-Agent System)
The core intelligence engine consisting of specialized LangChain-based agents:
- 👑 **Supervisor Agent (`supervisor_agent.py`)**: The central orchestrator routing tasks and managing the execution flow.
- 🗺️ **Orchestration Planner (`orchestration_planner.py`)**: Deconstructs complex medical scenarios into executable sub-tasks.
- 🧠 **Reasoning Agent (`reasoning_agent.py`)**: Synthesizes retrieved evidence against patient vitals to generate differential diagnoses.
- 🔍 **Retrieval Agent (`retrieval_agent.py`)**: Fetches relevant medical literature and patient context.
- ⚖️ **Validation Agent (`validation_agent.py`)**: Cross-references outputs against established medical knowledge to prevent hallucinations.
- 🪞 **Reflection Agent (`reflection_agent.py`)**: Critiques reasoning outputs. Triggers a "replan" if logic flaws are detected.

### 4. Safety & Guardrails Layer
A dedicated deterministic layer intercepting data at the API and agent execution levels:
- **`InputGuardrail`**: Scans for explicit safety violations and sanitizes PII.
- **`OutputGuardrail`**: Prevents the system from confidently asserting unverified medical advice.
- **`ClinicalGuardrail`**: Enforces rules on clinical scope (prevents autonomous prescription).
- **`PromptGuardrail`**: Protects the agentic system from prompt injection attacks.

### 5. Knowledge & RAG Layer
Implements a dual-retrieval approach:
- **GraphRAG**: Maps clinical entities (Symptoms, Diseases, Medications) into structured Graphs using Cypher templates for precise semantic querying.
- **Dense Vector Search**: Retrieves unstructured textbook knowledge and literature.
- **External Clients**: Live querying of `pubmed_client.py` and `clinical_trials_client.py` for cutting-edge peer-reviewed studies.

### 6. Telemetry & Evaluation Layer
- **`failure_analytics.py` & `grounding_engine.py`**: Calculates the confidence of outputs and penalizes the system for cross-source contradictions.
- **`orchestration_trace.py` & `agent_telemetry.py`**: Provides live tracing of the decision-making process.

---

## 🔄 End-to-End Data Flow

1. **Intake**: Clinician inputs patient data (e.g., "65yo M, chest pain, BP 160/100") or uploads an ECG.
2. **Intent & Sanitize**: Frontend categorizes intent. FastAPI receives the payload; Input Guardrails sanitize the data.
3. **Orchestration**: The Supervisor Agent creates an execution plan.
4. **Retrieval**: The Retrieval Agent fetches graph data and live medical literature.
5. **Reasoning & Reflection**: The Reasoning agent generates a differential diagnosis. Reflection and Validation agents critique it.
6. **Streaming**: Telemetry streams status updates back to the UI in real-time.
7. **Governance Delivery**: The final clinical report is delivered alongside a Confidence Label. Low confidence triggers "Clinician Approval Escalated."

---

## 🚀 Getting Started

### Prerequisites
- Node.js (v18+)
- Python (v3.11+)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/pavandoddavarapu/aegis_agenticAi_capstone.git
cd aegis_agenticAi_capstone
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```
*Note: Ensure you configure your `.env` variables for API keys and database connections before running.*

Start the FastAPI server:
```bash
uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd ../frontend
npm install
npm run dev
```

The application will be available at `http://localhost:3000`.

---
*Disclaimer: Aegis is a Clinical Decision Support System. It is intended to assist, not replace, professional medical judgment.*
