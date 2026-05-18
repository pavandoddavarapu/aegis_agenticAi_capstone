# Aegis Clinical Intelligence System

Aegis is an advanced Clinical AI platform designed for clinical intelligence, agentic workflows, medical retrieval-augmented generation (RAG), and clinical validation.

## Repository Structure

```text
aegis-clinical-ai/
│
├── backend/
│   ├── api/             # FastAPI routes and endpoints
│   ├── agents/          # Agent architectures and clinical agents
│   ├── orchestration/   # Multi-agent coordination and workflows
│   ├── rag/             # Retrieval-augmented generation & search
│   ├── validation/      # Clinical accuracy & guardrails
│   ├── workflows/       # LangGraph and state workflows
│   ├── memory/          # Short and long-term memory
│   ├── observability/   # Tracing, logging, and evaluation
│   ├── models/          # Data schemas and model definitions
│   ├── utils/           # Shared utility functions
│   └── main.py          # FastAPI application entrypoint
│
├── frontend/            # Next.js or Vite React interface
├── docker/              # Docker configuration files
├── docs/                # Project documentation and specifications
├── tests/               # Unit, integration, and clinical tests
│
├── .env                 # Environment variables configuration
├── requirements.txt     # Python core dependencies
├── docker-compose.yml   # Multi-container orchestration (Qdrant, Redis, Postgres)
└── README.md            # Project overview & documentation
```

## Getting Started

### 1. Setup Virtual Environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Infrastructure Containers

Ensure Docker is running, then start the services:

```bash
docker-compose up -d
```

This will run:
- **Qdrant Vector DB** on port `6333`
- **Redis Cache/Memory** on port `6379`
- **Postgres Database** on port `5432`

### 4. Run the Backend API

```bash
uvicorn backend.main:app --reload
```

The API will be available at `http://127.0.0.1:8000` with interactive documentation at `http://127.0.0.1:8000/docs`.
"# aegis_agenticAi_capstone" 
