# ⚕️ Aegis Clinical Intelligence Platform

<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-success.svg?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg?style=for-the-badge&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Next.js-14+-black.svg?style=for-the-badge&logo=next.js" alt="Next.js">
  <img src="https://img.shields.io/badge/FastAPI-0.109+-009688.svg?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Architecture-Multi--Agent-orange.svg?style=for-the-badge" alt="Multi-Agent">
</div>

<br />

Aegis is an advanced, multi-agent **Clinical Decision Support System (CDSS)** designed to assist healthcare professionals by orchestrating complex medical reasoning, multimodal evidence retrieval, and strict safety guardrails. With a stunning "Medical White" UI, Aegis acts as a powerful clinical copilot, providing evidence-based insights, differential diagnoses, and treatment pathways.

---

## ✨ Key Features

- 🧠 **Multi-Agent Orchestration**: A hierarchical network of specialized AI agents handling reasoning, retrieval, validation, and reflection.
- 🩺 **Clinical Guardrails**: Deterministic safety checks ensuring HIPAA compliance, safe outputs, and strict prompt adherence.
- 🕸️ **GraphRAG & Multimodal Retrieval**: Deep semantic search across medical literature, integrating unstructured text, OCR from medical imaging, and structured knowledge graphs.
- 🛡️ **Human-in-the-Loop (HITL)**: Confidence scoring and contradiction detection that escalates critical decisions to human clinicians.
- ⚡ **Real-Time Streaming**: Live streaming of the orchestration stages, giving transparency into the AI's "thought process."
- 🎨 **Medical White Aesthetic**: A clean, premium user interface designed specifically for clinical environments.

---

## 🏗️ Layered Architecture

Aegis is built on a robust, multi-layered architecture designed for scale, safety, and performance.

### 1. Presentation Layer (Frontend)
Built with **Next.js**, **React**, and **Tailwind CSS**. It features a modern, accessible, and responsive "Medical White" UI tailored for clinical settings. Includes interactive chat interfaces, real-time evidence scorecards, and live execution trace viewers.

### 2. API & Orchestration Layer (Backend)
Powered by **FastAPI**. This layer manages asynchronous API requests, websocket streaming, session context, and orchestrates the lifecycle of the Multi-Agent System.

### 3. Agentic Cognitive Layer (Multi-Agent System)
The core intelligence engine. Specialized agents work collaboratively to resolve complex clinical queries:
- 👑 **Supervisor Agent**: The orchestrator that routes tasks and manages the execution flow.
- 🧠 **Reasoning Agent**: Synthesizes medical information to generate hypotheses and clinical insights.
- 🔍 **Retrieval Agent**: Fetches relevant medical literature, guidelines, and patient context.
- ⚖️ **Validation Agent**: Cross-references outputs against established medical knowledge to prevent hallucinations.
- 🪞 **Reflection Agent**: Critiques the reasoning and suggests replanning if contradictions are found.
- 🗺️ **Orchestration Planner**: Breaks down complex medical queries into executable sub-tasks.

### 4. Safety & Guardrails Layer
A dedicated deterministic layer that intercepts data at the API and agent execution levels. Includes `InputGuardrail`, `OutputGuardrail`, `ClinicalGuardrail`, and `PromptGuardrail` to enforce safety and formatting.

### 5. Knowledge & RAG Layer
Implements **GraphRAG** (Graph Retrieval-Augmented Generation) and **Multimodal Retrieval** (OCR pipelines for X-Rays/ECGs). Converts clinical data into structured graphs using Cypher templates for precise semantic querying.

### 6. Telemetry & Evaluation Layer
Tracks multi-agent traces, logs orchestration events, and performs failure analytics to continuously monitor system performance and accuracy.

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
*Note: Ensure you configure your environment variables (e.g., `.env`) for API keys and database connections before running.*

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

## 🔬 Use Cases
- **Diagnostic Copilot**: "65-year-old male with crushing chest pain, BP 160/100, HR 95, diabetic. What is the differential diagnosis?"
- **Treatment Pathways**: Cross-reference patient vitals with the latest medical guidelines to suggest safe treatment plans.
- **Multimodal Intake**: Upload clinical files (ECG, X-Ray, PDF reports) for automated OCR and semantic extraction.

---

## 🛡️ Governance & Safety
Aegis prioritizes patient safety above all. The system uses a built-in **Clinical Grounding Score**. If confidence falls below the safe threshold, or if cross-source contradictions are found, the system immediately flags the case as **"Clinician Approval Escalated"** (Human-in-the-Loop required).

---
*Disclaimer: Aegis is a Clinical Decision Support System. It is intended to assist, not replace, professional medical judgment.*
