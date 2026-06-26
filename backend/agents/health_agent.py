"""
Health Agent — Tracks symptoms and generates health reports.
=============================================================

This agent handles the health monitoring side of MedMinder: symptom
tracking, medication adherence analysis, and generating comprehensive
reports for healthcare providers.

Architecture & Design Decisions:
---------------------------------
1. **Dual MCP server connection**: This agent connects to TWO MCP servers:
   - Custom MedMinder server: For symptom logging, adherence reports, and
     doctor summary generation (our own data)
   - healthcare-mcp-public: For medical calculators, health topic lookup,
     and ICD-10 code search (external reference data)

   This split keeps our custom server focused on MedMinder-specific data
   while leveraging existing open-source servers for general medical info.

2. **Clinical escalation logic**: The instruction prompt includes specific
   severity thresholds that trigger different agent behaviors:
   - Severity 1-3: Normal logging and tracking
   - Severity 4: Urgent — recommend contacting healthcare provider
   - Severity 5: Emergency — recommend calling emergency services
   This ensures the agent responds appropriately to critical symptoms.

3. **WHO-based adherence interpretation**: Adherence percentages are
   interpreted using World Health Organization guidelines:
   - ≥80%: Good adherence
   - 50-79%: Moderate — may need intervention
   - <50%: Poor — urgent intervention needed
   This gives users clinically meaningful context for their numbers.

4. **Report generation**: The doctor summary feature creates a comprehensive,
   printable report suitable for a medical appointment. This is a key
   differentiator for MedMinder — turning raw tracking data into actionable
   clinical summaries.

Available MCP Tools:
  From MedMinder server:
    - log_symptom: Record symptoms with severity and optional medication link
    - get_symptom_history: Retrieve recent symptoms for pattern analysis
    - get_adherence_report: Calculate adherence stats per medication
    - generate_doctor_summary: Create comprehensive provider report

  From healthcare-mcp-public (if available):
    - Medical calculators (BMI, eGFR, etc.)
    - Health topic lookup
    - ICD-10 code search

⚕️ MEDICAL DISCLAIMER:
  Symptom tracking and adherence reports are based on self-reported data.
  They are intended to supplement — not replace — clinical assessments.
  If you experience severe or emergency symptoms, contact emergency
  services immediately. Do not wait for an AI response.

Usage:
  from backend.agents.health_agent import create_health_agent
  agent = create_health_agent()
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

if TYPE_CHECKING:
    pass  # Reserved for future type-only imports

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("medminder.agents.health")

# ---------------------------------------------------------------------------
# Path to our custom MedMinder MCP server
# ---------------------------------------------------------------------------
# Same server as ScheduleAgent — MCP servers can handle multiple clients.
# Each agent gets its own subprocess instance of the server, sharing the
# same SQLite database file. SQLite handles concurrent reads safely, and
# writes are serialized by its built-in locking.
_MCP_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "mcp_servers",
    "medminder_server.py",
)


def _create_medminder_toolset() -> McpToolset:
    """Create a McpToolset for the custom MedMinder MCP server.

    This toolset provides access to symptom logging, adherence reporting,
    and doctor summary generation — all reading/writing to our local
    SQLite database.

    Returns:
        McpToolset connected to the MedMinder MCP server.

    Note:
        Unlike the external server connections, this one should always
        succeed since we control the server code. If it fails, it's a
        configuration error that should be surfaced immediately.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="python",
                args=[_MCP_SERVER_SCRIPT],
                # Pass through environment for DB_PATH and other config
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", ""),
                    "MEDMINDER_DB_PATH": os.environ.get("MEDMINDER_DB_PATH", ""),
                    "DB_PATH": os.environ.get("DB_PATH", ""),
                    "HOME": os.environ.get("HOME", "/tmp"),
                    "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", "/tmp/.cache"),
                },
            ),
            timeout=60,
        )
    )


def _create_healthcare_mcp_toolset() -> McpToolset | None:
    """Attempt to create a McpToolset for healthcare-mcp-public.

    Provides supplementary medical reference tools:
      - Medical calculators (BMI, eGFR, creatinine clearance)
      - Health topic information from trusted sources
      - ICD-10 diagnostic code lookup

    These tools enhance the Health Agent's reporting capabilities but
    are not strictly required for core functionality.

    Returns:
        McpToolset if available, None if healthcare-mcp is not installed.
    """
    try:
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "healthcare-mcp"],
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "NODE_PATH": os.environ.get("NODE_PATH", ""),
                        "HOME": os.environ.get("HOME", "/tmp"),
                        "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", "/tmp/.cache"),
                    },
                ),
                timeout=60,
            )
        )
        logger.info("healthcare-mcp-public toolset available for HealthAgent.")
        return toolset
    except Exception as e:
        logger.warning(
            "healthcare-mcp-public not available for HealthAgent: %s. "
            "Medical calculators and health topic lookup will not be "
            "available. Core symptom tracking and reporting still works. "
            "Install with: npm install -g healthcare-mcp",
            str(e),
        )
        return None


def create_health_agent() -> LlmAgent:
    """Create and return the Health Agent with MCP tools.

    This factory function builds the HealthAgent with connections to:
    1. The custom MedMinder MCP server (always required)
    2. healthcare-mcp-public (optional, for supplementary medical info)

    Returns:
        LlmAgent: A fully configured Health Agent ready to be used
                  as a sub-agent in the MedMinder orchestrator.
    """
    logger.info("Creating HealthAgent...")

    # -------------------------------------------------------------------
    # Collect MCP toolsets
    # -------------------------------------------------------------------
    tools_list: list[McpToolset] = []

    # Primary toolset: our custom MedMinder MCP server
    # This provides the core health tracking tools (symptoms, adherence,
    # doctor summaries). It's required — if this fails, we should know.
    medminder_mcp = _create_medminder_toolset()
    tools_list.append(medminder_mcp)
    logger.info("MedMinder MCP toolset connected for HealthAgent.")

    # Secondary toolset: healthcare-mcp-public (optional enhancement)
    healthcare_mcp = _create_healthcare_mcp_toolset()
    if healthcare_mcp:
        tools_list.append(healthcare_mcp)

    # -------------------------------------------------------------------
    # Build the Health Agent
    # -------------------------------------------------------------------
    health_agent = LlmAgent(
        name="HealthAgent",

        # gemini-2.5-flash for fast responses. Report generation might
        # benefit from a more capable model, but flash handles it well
        # since the heavy lifting is done by the MCP tools.
        model="gemini-2.5-flash",

        # Description for the orchestrator's routing logic.
        # Keywords: symptoms, adherence, reports, doctor, health tracking
        description=(
            "Tracks symptoms and side effects, monitors medication adherence, "
            "generates health reports and doctor summaries. Use this agent when "
            "the user wants to: report a symptom or side effect, check their "
            "medication adherence, prepare a report for their doctor, review "
            "their symptom history, or get health tracking insights."
        ),

        # Comprehensive instruction prompt covering:
        #   - Symptom logging with severity scale
        #   - Escalation thresholds for critical symptoms
        #   - Adherence interpretation using WHO guidelines
        #   - Doctor summary generation guidance
        #   - Medical disclaimers throughout
        instruction="""You are the Health Agent for MedMinder, specializing in health monitoring and reporting.

Your responsibilities span three key areas: symptom tracking, adherence monitoring,
and health report generation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. SYMPTOM TRACKING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use log_symptom(user_id, description, severity, related_medication) to record symptoms.

SEVERITY SCALE (always explain this to users when they report symptoms):
  1 ⬜ Minimal   — Barely noticeable, no impact on daily activities
  2 🟨 Mild      — Noticeable but doesn't prevent normal activities
  3 🟧 Moderate  — Affects some daily activities or causes discomfort
  4 🟥 Severe    — Significantly limits daily activities, very uncomfortable
  5 🚨 Emergency — Requires immediate medical attention

ESCALATION RULES (these are NON-NEGOTIABLE):
  • Severity 1-3: Log normally. Offer to note which medication might be related.
  • Severity 4: ⚠️ URGENT — Log the symptom, then STRONGLY recommend the user
    contact their healthcare provider as soon as possible. Ask if they need help
    finding their provider's contact information.
  • Severity 5: 🚨 EMERGENCY — Log the symptom, then IMMEDIATELY advise calling
    emergency services (911 in US). Do NOT continue with casual conversation.
    Make the emergency recommendation PROMINENT and UNMISSABLE.

When logging symptoms:
  - Ask clarifying questions to get an accurate description
  - Help users rate severity using the scale above
  - Always ask if they think it might be medication-related
  - Look for patterns: "Is this the first time?" or "How often does this happen?"

Use get_symptom_history(user_id, days) to review past symptoms and identify patterns.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2. ADHERENCE MONITORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use get_adherence_report(user_id, days) to generate adherence statistics.

ADHERENCE INTERPRETATION (based on WHO guidelines):
  ✅ ≥ 80%  — GOOD adherence. Praise the user! Consistent medication taking
              is one of the most impactful health behaviors.
  ⚠️ 50-79% — MODERATE adherence. Gently explore barriers:
              - Are they forgetting? → Suggest reminders or pill organizers
              - Side effects? → Recommend discussing with their doctor
              - Cost issues? → Suggest talking to their pharmacist about alternatives
              - Feeling better? → Explain why consistent dosing matters
  🔴 < 50%  — POOR adherence. This needs attention:
              - Express concern without judgment
              - Identify the primary barrier
              - Strongly recommend discussing with their healthcare provider
              - Offer to help set up a more manageable schedule

When presenting adherence data:
  - Show per-medication percentages clearly
  - Highlight trends (improving, declining, stable)
  - Calculate and show overall adherence across all medications
  - Use the common period options: 7 days (weekly), 30 days (monthly), 90 days (quarterly)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
3. DOCTOR SUMMARIES & REPORTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Use generate_doctor_summary(user_id, patient_name, days) for comprehensive reports.

When generating a doctor summary:
  - Ask for the patient's name if not provided (for the report header)
  - Default to 30-day lookback, but offer 7-day or 90-day options
  - Explain what the report includes and how to share it with their doctor
  - Remind the user that this supplements but doesn't replace medical records

The doctor summary includes:
  ✓ Current medication list with dosages and schedules
  ✓ Adherence statistics per medication
  ✓ Recent symptom reports with severity and timing
  ✓ Medical disclaimer about self-reported data

DEFAULT BEHAVIORS:
━━━━━━━━━━━━━━━━━
• Always use user_id 'default_user' unless the user specifies otherwise
• When a user reports a symptom, walk them through the severity scale
• For adherence queries, default to 30-day period unless specified
• Be encouraging about good adherence, gentle about poor adherence
• Always offer follow-up actions after presenting data

⚕️ MEDICAL DISCLAIMER:
All health data in MedMinder is self-reported by the user. Symptom
severity ratings are subjective assessments, not clinical diagnoses.
Adherence percentages may not reflect actual medication intake.
This information is meant to support — not replace — conversations
with healthcare providers. Always recommend professional medical
evaluation for health concerns.""",

        # Tools from both MCP servers (MedMinder + optional healthcare-mcp)
        tools=tools_list,
    )

    logger.info(
        "HealthAgent created with %d MCP toolset(s).",
        len(tools_list),
    )
    return health_agent
