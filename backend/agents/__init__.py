"""
MedMinder Agent System — Multi-agent architecture using Google ADK.
====================================================================

This package implements a multi-agent medication management system using
Google's Agent Development Kit (ADK). The architecture follows a hub-and-spoke
pattern with one orchestrator routing to three specialist agents:

  MedMinder (Orchestrator)
  ├── ScheduleAgent  — Medication scheduling, dose logging, reminders
  ├── InteractionAgent — Drug interaction checks, FDA info, safety alerts
  └── HealthAgent    — Symptom tracking, adherence reports, doctor summaries

Quick Start:
  # Create the complete agent system:
  from backend.agents import create_root_agent
  root = create_root_agent()

  # Use with ADK's InMemoryRunner:
  from google.adk.runners import InMemoryRunner
  runner = InMemoryRunner(agent=root)

Why a factory function instead of a module-level instance?
  - MCP connections spawn subprocesses — can't do that at import time
  - Avoids side effects during test collection (pytest imports all modules)
  - Allows multiple independent agent systems in the same process
  - Makes dependency injection straightforward for testing

⚕️ MEDICAL DISCLAIMER:
  MedMinder is for informational and tracking purposes only. It is NOT
  a medical device and does NOT constitute medical advice.
"""

from .orchestrator import create_root_agent

__all__ = ["create_root_agent"]
