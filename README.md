# 💊 MedMinder

### AI-Powered Medication Management Agent

> An intelligent multi-agent system that helps patients manage medications safely—tracking schedules, checking drug interactions, monitoring symptoms, and generating doctor-ready reports—all through natural conversation.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Google ADK](https://img.shields.io/badge/Google-ADK-4285F4?logo=google&logoColor=white)](https://google.github.io/adk-docs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Track: Concierge](https://img.shields.io/badge/Track-Concierge-purple)](https://www.kaggle.com/)
[![MCP Servers: 5](https://img.shields.io/badge/MCP_Servers-5_(4%20existing%20%2B%201%20custom)-orange)](https://modelcontextprotocol.io/)

---

## 📑 Table of Contents

- [🎯 Problem Statement](#-problem-statement)
- [💡 Solution](#-solution)
- [🏗️ Architecture](#%EF%B8%8F-architecture)
- [🔧 Course Concepts Demonstrated](#-course-concepts-demonstrated)
- [🚀 Quick Start](#-quick-start)
- [📱 Features](#-features)
- [🧪 Testing](#-testing)
- [📁 Project Structure](#-project-structure)
- [🛡️ Security](#%EF%B8%8F-security)
- [⚕️ Medical Disclaimer](#%EF%B8%8F-medical-disclaimer)
- [🙏 Acknowledgments](#-acknowledgments)
- [📄 License](#-license)

---

## 🎯 Problem Statement

Medication non-adherence is a **global health crisis** hiding in plain sight:

| Statistic | Impact |
|---|---|
| **50%** of medications are not taken as prescribed | Leads to 125,000+ preventable deaths/year in the US alone |
| **$300 billion** in avoidable healthcare costs annually | From medication-related hospital admissions |
| **Drug interactions** cause 125,000+ deaths annually in the US | Many patients take 5+ medications with unknown interactions |
| **Patients forget** medications, miss doses, don't track side effects | No easy way to maintain a medication diary |
| **Doctor visits** are stressful and disorganized | Patients can't recall symptoms, adherence, or medication history |

The people most affected—elderly patients, those on complex multi-drug regimens, and caregivers—need a simple, intelligent assistant that works through natural conversation, not complicated apps with tiny buttons and confusing interfaces.

---

## 💡 Solution

**MedMinder** is an AI-powered medication management agent that acts as your personal health concierge. Through natural conversation, it:

- 📋 **Manages medication schedules** — add, remove, and track all your prescriptions
- ⚠️ **Checks drug interactions** — queries BioMCP and DDInter for safety data
- 📊 **Tracks adherence** — monitors doses taken, missed, and late with statistics
- 🩺 **Generates doctor reports** — creates printable summaries for appointments
- 😷 **Monitors symptoms** — logs side effects with severity ratings and correlations
- 📅 **Schedules reminders** — integrates with Google Calendar for dose notifications

### What makes MedMinder different?

- **Multi-Agent Architecture** — Built with Google ADK, using specialized sub-agents that each excel at one job (scheduling, interactions, health monitoring)
- **5 MCP Servers** — Connects to 4 existing MCP servers (BioMCP, DDInter, Healthcare-MCP, Google Calendar) plus 1 custom-built MedMinder MCP server
- **Privacy-First** — All health data stays local in SQLite; only LLM queries go to the Gemini API
- **User-Provided API Key** — No server-stored credentials; the user brings their own Gemini key

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MedMinder Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     HTTP      ┌──────────────┐                           │
│  │   Frontend   │ ────────────► │   FastAPI     │                           │
│  │  (HTML/CSS/  │ ◄──────────── │   Server      │                           │
│  │   Vanilla JS)│    JSON       │   :8000       │                           │
│  └──────────────┘               └──────┬───────┘                           │
│                                        │                                    │
│                                        │ ADK Runner                         │
│                                        ▼                                    │
│                              ┌──────────────────┐                           │
│                              │   Orchestrator    │ ◄── Gemini 2.0 Flash     │
│                              │   (Root Agent)    │                           │
│                              └────────┬─────────┘                           │
│                                       │                                     │
│                    ┌──────────────────┼──────────────────┐                  │
│                    │ routes by intent │                   │                  │
│                    ▼                  ▼                   ▼                  │
│          ┌─────────────────┐ ┌────────────────┐ ┌────────────────┐         │
│          │ ScheduleAgent   │ │ Interaction    │ │  HealthAgent   │         │
│          │                 │ │   Agent        │ │                │         │
│          │ • Add/remove    │ │ • Drug-drug    │ │ • Log symptoms │         │
│          │   medications   │ │   interaction  │ │ • Adherence    │         │
│          │ • Log doses     │ │   checks       │ │   reports      │         │
│          │ • Daily schedule│ │ • FDA/PubMed   │ │ • Doctor       │         │
│          │ • Calendar sync │ │   lookups      │ │   summaries    │         │
│          └────────┬────────┘ └───────┬────────┘ └───────┬────────┘         │
│                   │                  │                   │                  │
│          ┌────────▼────────┐ ┌───────▼────────┐ ┌───────▼────────┐         │
│          │  MedMinder MCP  │ │   BioMCP       │ │  MedMinder MCP │         │
│          │  (Custom)       │ │   DDInter      │ │  (Custom)      │         │
│          │                 │ │   Healthcare   │ │                │         │
│          │  Google Calendar│ │   MCP          │ │                │         │
│          │  MCP            │ │                │ │                │         │
│          └────────┬────────┘ └───────┬────────┘ └───────┬────────┘         │
│                   │                  │                   │                  │
│                   └──────────────────┼───────────────────┘                  │
│                                      ▼                                     │
│                              ┌──────────────┐                              │
│                              │   SQLite DB   │ ← Local, privacy-first      │
│                              │  (medminder   │                              │
│                              │    .db)       │                              │
│                              └──────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User** types a natural-language message in the web chat interface
2. **FastAPI** server receives the request and passes it to the ADK Runner
3. **Orchestrator** (root agent) analyzes intent and routes to the appropriate sub-agent
4. **Sub-agent** uses its MCP server tools to read/write data and query external sources
5. **Response** flows back through the orchestrator to the user, with medical disclaimers

---

## 🔧 Course Concepts Demonstrated

| # | Concept | Implementation | Details |
|---|---------|---------------|---------|
| 1 | **Multi-Agent System** | Google ADK `LlmAgent` with `sub_agents` | Root orchestrator + 3 specialist agents (ScheduleAgent, InteractionAgent, HealthAgent) with LLM-based intent routing |
| 2 | **MCP Server** | 1 custom + 4 existing MCP servers | Custom `medminder_server.py` (FastMCP, 10 tools) + BioMCP + DDInter + Healthcare-MCP + Google Calendar MCP |
| 3 | **Antigravity** | End-to-end application with web UI | Full-stack: HTML/CSS/JS frontend → FastAPI backend → ADK agents → MCP tools → SQLite DB |
| 4 | **Security** | Privacy-first architecture | API keys in-memory only, health data local-only (SQLite), input validation, medical disclaimers, `.gitignore` protections |
| 5 | **Deployability** | Docker + docker-compose | Multi-stage Dockerfile, health checks, volume persistence, environment configuration, one-command startup |
| 6 | **Agent Skills** | Specialized agent capabilities | Drug interaction checking (BioMCP/DDInter), adherence reporting, doctor summary generation, symptom correlation, emergency protocols |

> ✅ **6/6 course concepts covered**

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Backend, agents, MCP server |
| Node.js | 18+ | Healthcare-MCP and Google Calendar MCP servers (optional) |
| Gemini API Key | Free | LLM operations — get one at [aistudio.google.com](https://aistudio.google.com/) |

### Option 1: Docker (Recommended)

The fastest way to get MedMinder running:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/medminder.git
cd medminder

# Set your API key (or provide it via the frontend later)
export GOOGLE_API_KEY="your-gemini-api-key-here"

# Build and run with Docker Compose
docker-compose up --build

# Open your browser
# → http://localhost:8000
```

### Option 2: Local Setup

For development or if you prefer not to use Docker:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/medminder.git
cd medminder

# Create and activate a Python virtual environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

# Install Python dependencies
pip install -r backend/requirements.txt

# (Optional) Install external MCP servers for full functionality
pip install biomcp-cli            # BioMCP for drug interactions & PubMed
# npm install -g healthcare-mcp  # Healthcare MCP for FDA data (optional)

# Create your environment configuration
cp backend/.env.example backend/.env
# Edit backend/.env and add your GOOGLE_API_KEY

# Run the server
python -m backend.server

# Open your browser
# → http://localhost:8000
```

### First-Time Setup

1. Open `http://localhost:8000` in your browser
2. Click the **⚙️ Settings** icon in the top-right corner
3. Paste your **Gemini API Key** (get one free at [aistudio.google.com](https://aistudio.google.com/))
4. Start chatting! Try: *"Add Lisinopril 10mg, once daily at 8am"*

---

## 📱 Features

| Feature | Description |
|---|---|
| 💬 **Chat Interface** | Natural-language medication management — just talk to MedMinder like you would a pharmacist |
| 💊 **Medication Tracking** | Add, remove, and list medications with dosage, frequency, and scheduling |
| 📝 **Dose Logging** | Record taken, missed, or late doses with timestamps and notes |
| ⚠️ **Drug Interaction Checking** | Query BioMCP and DDInter databases for drug-drug interactions and safety alerts |
| 📊 **Adherence Reports** | Track dose compliance over time with percentage statistics per medication |
| 🩺 **Doctor Summaries** | Generate printable, comprehensive health reports for medical appointments |
| 😷 **Symptom Tracking** | Log symptoms with severity ratings (1-5) and medication correlations |
| 📅 **Google Calendar Reminders** | Schedule medication reminder events in Google Calendar (OAuth required) |
| 🚨 **Emergency Protocols** | Automatic escalation for severity-5 symptoms with emergency contact guidance |
| 🔒 **Privacy-First** | All health data stored locally in SQLite — never transmitted to cloud storage |
| 🎨 **Responsive Dashboard** | Clean web UI with medication list, daily schedule, and chat in one view |
| ⚕️ **Medical Disclaimers** | Prominent safety notices on all responses — MedMinder never replaces a doctor |

---

## 🧪 Testing

MedMinder uses **BDD (Behavior-Driven Development)** with pytest-bdd for human-readable test scenarios:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=backend --cov-report=html

# Run specific feature tests
pytest tests/ -k "drug_interactions" -v
pytest tests/ -k "medication_tracking" -v
pytest tests/ -k "adherence" -v

# Open the HTML coverage report
open htmlcov/index.html        # macOS
# xdg-open htmlcov/index.html  # Linux
```

### Test Categories

| Category | What's Tested |
|---|---|
| Medication CRUD | Adding, removing, listing medications via MCP tools |
| Dose Logging | Recording taken/missed/late doses with validation |
| Drug Interactions | BioMCP and DDInter queries for interaction data |
| Adherence Reports | Statistical calculations over configurable time periods |
| Doctor Summaries | Report generation with formatted output |
| Symptom Tracking | Severity validation, emergency escalation |
| API Endpoints | FastAPI routes, error handling, input validation |

---

## 📁 Project Structure

```
medminder/
├── README.md                          # ← You are here
├── LICENSE                            # MIT License
├── Dockerfile                         # Multi-stage Docker build
├── docker-compose.yml                 # One-command deployment
├── .gitignore                         # Protects secrets, DB, caches
│
├── backend/                           # Python backend (FastAPI + ADK)
│   ├── __init__.py
│   ├── server.py                      # FastAPI app — API endpoints, static serving
│   ├── config.py                      # Environment configuration management
│   ├── requirements.txt               # Python dependencies
│   │
│   ├── agents/                        # Google ADK multi-agent system
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # Root agent — intent routing to sub-agents
│   │   ├── schedule_agent.py          # Medication schedules, dose logging
│   │   ├── interaction_agent.py       # Drug interaction checking (BioMCP/DDInter)
│   │   └── health_agent.py            # Symptoms, adherence, doctor reports
│   │
│   ├── db/                            # Database layer (async SQLite)
│   │   ├── __init__.py
│   │   ├── database.py                # MedMinderDB — all CRUD operations
│   │   └── models.py                  # Pydantic models for type safety
│   │
│   └── mcp_servers/                   # MCP server implementations
│       ├── __init__.py
│       └── medminder_server.py        # ★ Custom MCP server (10 tools, FastMCP)
│
├── frontend/                          # Web UI (vanilla HTML/CSS/JS)
│   ├── index.html                     # Single-page application
│   ├── css/
│   │   └── style.css                  # Responsive design, medical theme
│   └── js/
│       ├── app.js                     # Main application logic
│       ├── api.js                     # API client (fetch wrapper)
│       └── components.js             # UI component rendering
│
└── tests/                             # BDD test suite (pytest-bdd)
    ├── __init__.py
    ├── features/                      # Gherkin .feature files
    └── step_defs/                     # Step definitions
        └── __init__.py
```

---

## 🛡️ Security

MedMinder takes a **privacy-first approach** to health data:

| Security Measure | Implementation |
|---|---|
| **Local Data Storage** | All health data (medications, doses, symptoms) stored in local SQLite — never transmitted to cloud storage services |
| **In-Memory API Keys** | Gemini API keys stored in memory only — never written to disk or database |
| **No Server-Side Key Storage** | Users provide their own API keys — MedMinder never stores or manages cloud credentials on the server |
| **Input Validation** | Pydantic models validate all API inputs with length limits and type checking |
| **`.gitignore` Protection** | Database files (`.db`), environment files (`.env`), API keys, and Python caches are all gitignored |
| **Medical Disclaimers** | Every agent response includes a disclaimer that MedMinder is not medical advice |
| **CORS Configuration** | Configurable CORS middleware (open for demo, restrict for production) |
| **Error Sanitization** | Error messages provide helpful guidance without exposing system internals |

### What MedMinder Does NOT Do

- ❌ Does **not** store API keys on disk
- ❌ Does **not** transmit health data to external storage
- ❌ Does **not** require user authentication (single-user demo)
- ❌ Does **not** claim to be a medical device or provide medical advice

---

## ⚕️ Medical Disclaimer

> [!CAUTION]
> **MedMinder is for INFORMATIONAL and EDUCATIONAL purposes only.**
>
> It is **NOT** a medical device, **NOT** FDA approved, and **NOT** a substitute for professional medical advice, diagnosis, or treatment.
>
> - **Do not** make medication decisions based solely on MedMinder's output
> - **Do not** change dosages without consulting your healthcare provider
> - **Do not** ignore professional medical advice because of information from this app
> - **Always** consult your physician or pharmacist before starting, stopping, or changing any medication
> - **Always** seek emergency care for severe symptoms (call 911 or your local emergency number)
>
> All drug interaction data comes from third-party databases (BioMCP, DDInter) and may not be complete or current. Adherence statistics are based on self-reported data.
>
> **If you are experiencing a medical emergency, call 911 immediately.**

---

## 🙏 Acknowledgments

- **[Kaggle AI Agents Intensive Course](https://www.kaggle.com/)** — For the curriculum, community, and inspiration
- **[Google ADK Team](https://google.github.io/adk-docs/)** — For the Agent Development Kit that powers multi-agent orchestration
- **[BioMCP](https://github.com/genomoncology/biomcp)** by GenomOncology — Drug interactions, clinical trials, and PubMed access via MCP
- **[FastMCP](https://github.com/jlowin/fastmcp)** — The elegant Python framework for building MCP servers
- **[DDInter](http://ddinter.scbdd.com/)** — Drug-drug interaction database
- **[Model Context Protocol](https://modelcontextprotocol.io/)** — The open standard that makes tool interoperability possible
- All open-source MCP server authors who make the ecosystem thrive

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ for the Kaggle AI Agents Intensive Capstone
  <br>
  <em>Because everyone deserves a little help managing their health.</em>
</p>
