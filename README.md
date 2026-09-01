# Margdarshak AI (मार्गदर्शक) 🚀
### Agentic Placement Readiness & Career Intelligence System

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![Gemini](https://img.shields.io/badge/Gemini_LLM-3.6_Flash-purple.svg)](https://deepmind.google/technologies/gemini/)
[![License](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)

**Margdarshak AI** (*Sanskrit*: **मार्गदर्शक** — *The Pathfinder*) is an **agentic, multi-layered AI application** designed to guide students through university campus placement preparations. Driven by **Gemini 3.6 Flash LLM** and backed by a deterministic rule-based calculation engine, it provides personalized, high-fidelity career roadmaps, skill gap analysis, and long-term historical placement insights.

Created & Developed by **Rishi Kulkarni**  
📧 **Support / Contact**: `learn.rishipk@gmail.com`

---

## ✨ Key Features & Capabilities

- 🤖 **Agentic Clarification Loop (`PlannerAgent`)**: Interactively detects vague user requests and clarifies missing intent before generating career plans.
- 🔑 **Bring Your Own Gemini API Key (BYO-API)**: Users can supply their own Gemini API key directly via the interactive Web UI header (saved securely in LocalStorage), bypassing server quota constraints.
- 🎨 **Modern Web Portal**: Glassmorphism dark theme interface with live circular score gauges, real-time student registration, interactive agent chat, and vector memory visualization.
- 🛡️ **Governed Data Access (`PlacementConnector`)**: Enforces strict role-based access control (`student`, `placement_officer`, `system`).
- 🧠 **ChromaDB Long-Term Vector Memory (`RetrievalStore`)**: Retrieves historically similar student placement cases using semantic search to provide realistic benchmark insights.
- ⚡ **100% Fail-Proof Fallback Engine**: Seamlessly falls back to deterministic heuristic algorithms if LLM quotas are exceeded or network connectivity is offline.

---

## 🏛️ Architecture Overview

```text
                                  USER REQUEST
                                       |
                                       v
                             +--------------------+
                             |  Placement         |  ← Bring Your Own API Key Header
                             |  Coordinator       |
                             +---------+----------+
                                       |
                                       v
                                LAB 1 PLANNER      ← PlannerAgent (Gemini 3.6 Flash)
                                       |
                                       v
                                LAB 2 TOOLS
                         /-------------|-------------\
                        v              v              v
                   Student Data    Role Data      Readiness
                  (profile_tools) (role_tools)  (readiness_tools)
                                       |
                                       v
                                LAB 3 SKILLS
                              /             \
                         PlanSkill       FormatSkill (Gemini AI Summary)
                              |
                              v
                            LAB 4
                     MEMORY & RETRIEVAL
                      /               \
                 SessionMemory     RetrievalStore
                 (ephemeral)       (ChromaDB Vector Store)
                                      |
                                      v
                                   LAB 5
                            PLACEMENT CONNECTOR
                             /        |        \
                            v         v         v
                       Profiles     Roles   Assessments
                      (JSON / DB) (JSON / DB) (JSON / DB)
```

---

## 📁 Repository Structure

```text
Margdarshak-AI/
│
├── app/
│   ├── main.py                    # FastAPI web server & endpoints
│   ├── coordinator/
│   │   └── coordinator.py         # Top-level PlacementCoordinator
│   ├── agents/
│   │   └── planner_agent.py       # Agent clarification & plan creation
│   ├── models/
│   │   ├── schemas.py             # Domain models (Pydantic v2)
│   │   └── state.py               # Short-term RunState tracking
│   ├── tools/
│   │   ├── profile_tools.py       # Student profile tools
│   │   ├── role_tools.py          # Role requirements tools
│   │   └── readiness_tools.py     # Deterministic scoring engine
│   ├── skills/
│   │   ├── plan_skill.py          # Reusable PlanSkill
│   │   └── format_skill.py        # Executive summary & report builder
│   ├── memory/
│   │   ├── session_memory.py      # Short-term session memory
│   │   └── retrieval_store.py     # ChromaDB vector retrieval
│   ├── connector/
│   │   └── placement_connector.py # Governed data security layer
│   ├── services/
│   │   ├── llm_service.py         # Gemini 3.6 Flash integration & BYO-API
│   │   └── workflow_service.py    # Pipeline execution sequence
│   └── static/
│       ├── index.html             # Web Application Frontend
│       ├── styles.css             # Glassmorphism Design System
│       └── app.js                 # Frontend Application Logic
│
├── data/                          # Data persistence layer
│   ├── students.json
│   ├── roles.json
│   ├── skill_assessments.json
│   └── placement_history.json
│
├── tests/                         # Comprehensive pytest test suite (76 tests)
│   ├── test_lab1.py
│   ├── test_lab2.py
│   ├── test_lab3.py
│   ├── test_lab4.py
│   └── test_lab5.py
│
├── demo.py                        # Terminal CLI demonstration
├── requirements.txt               # Dependencies
└── README.md                      # Documentation
```

---

## ⚙️ Setup & Installation

### 1. Clone & Environment Setup

```bash
git clone https://github.com/geeky-rish/Margdarshak-AI.git
cd Margdarshak-AI

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Gemini API Key (Optional)

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
LLM_ENABLED=true
```

> **Note**: You can also skip setting `.env` and paste your Gemini API key directly into the **Web UI header**!

---

## 🚀 Running the Web Portal

```bash
uvicorn app.main:app --reload
```

Open your browser at [http://localhost:8000](http://localhost:8000) to access the interactive web application!

---

## 🧪 Running Unit Tests

To run the complete offline test suite (76 tests):

```bash
pytest
```

---

## 👤 Author & Support

- **Creator & Developer**: Rishi Kulkarni
- **Support Email**: `learn.rishipk@gmail.com`
- **GitHub**: [@geeky-rish](https://github.com/geeky-rish)

---
*Built with passion for agentic AI architectures.*
