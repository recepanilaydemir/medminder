"""
Schedule Agent — Manages medication timing and reminders.
==========================================================

This agent is responsible for all medication scheduling operations within
the MedMinder multi-agent system. It connects to the custom MedMinder MCP
server to access medication data, dose logging, and schedule management.

Architecture & Design Decisions:
---------------------------------
1. **MCP-first data access**: Rather than importing database functions
   directly, this agent communicates with the MedMinder MCP server over
   stdio. This enforces a clean protocol boundary — the agent layer
   never touches the database directly. Benefits:
     - The MCP server can be replaced or upgraded independently
     - Tools are discoverable at runtime via MCP's tool listing
     - Same server can be shared with other MCP clients (Claude Desktop, etc.)

2. **Single-responsibility**: This agent ONLY handles scheduling concerns.
   Drug interactions go to InteractionAgent, symptom tracking goes to
   HealthAgent. The orchestrator routes requests to the right specialist.

3. **McpToolset as tool provider**: Google ADK's McpToolset wraps an MCP
   connection and exposes all MCP tools as native ADK tools. The agent
   sees them as regular tools in its tool list — no custom adapters needed.

4. **StdioConnectionParams**: We spawn the MCP server as a subprocess
   using stdio transport. This is the simplest deployment model — no
   network ports, no authentication. The subprocess lifecycle is managed
   by ADK's MCP session manager.

5. **Environment passthrough**: We pass the current process's environment
   to the MCP subprocess so it inherits MEDMINDER_DB_PATH, GOOGLE_API_KEY,
   and other configuration from the parent process or .env file.

Available MCP Tools (from MedMinder server):
  - add_medication: Add a new medication to tracking
  - remove_medication: Deactivate a medication (soft delete)
  - list_medications: List all active medications for a user
  - log_dose: Record a dose as taken, missed, or late
  - log_missed_dose: Convenience tool for missed doses with reason
  - get_todays_schedule: Get today's schedule with completion status

⚕️ MEDICAL DISCLAIMER:
  This agent provides medication schedule tracking for INFORMATIONAL
  purposes only. It is NOT a medical device and does NOT constitute
  medical advice. Users should always follow their healthcare provider's
  instructions regarding medication timing and dosage.

Usage:
  from backend.agents.schedule_agent import create_schedule_agent
  agent = create_schedule_agent()
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
# Module-level logger — logs to stderr to avoid interfering with MCP stdio
# ---------------------------------------------------------------------------
logger = logging.getLogger("medminder.agents.schedule")

# ---------------------------------------------------------------------------
# Path to our custom MedMinder MCP server
# ---------------------------------------------------------------------------
# We resolve this relative to THIS file's location so it works regardless
# of the working directory when the agent system is started.
# Layout: backend/agents/schedule_agent.py → ../mcp_servers/medminder_server.py
_MCP_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "mcp_servers",
    "medminder_server.py",
)


def create_schedule_agent() -> LlmAgent:
    """Create and return the Schedule Agent with MCP tools.

    This factory function builds the ScheduleAgent with a live connection
    to the MedMinder MCP server. The MCP server is spawned as a child
    process using stdio transport when the agent first needs to use a tool.

    Returns:
        LlmAgent: A fully configured Schedule Agent ready to be used
                  as a sub-agent in the MedMinder orchestrator.

    Architecture Note:
        We use a factory function rather than a module-level agent instance
        because MCP connections involve async I/O and subprocess management.
        Creating the agent lazily via a factory avoids import-time side effects
        and makes testing easier (you can mock create_schedule_agent).
    """
    logger.info(
        "Creating ScheduleAgent with MCP server at: %s",
        _MCP_SERVER_SCRIPT,
    )

    # -------------------------------------------------------------------
    # Connect to the custom MedMinder MCP server
    # -------------------------------------------------------------------
    # McpToolset wraps an MCP connection and exposes all the server's
    # tools as native ADK tools. When the LlmAgent needs to call a tool,
    # ADK handles the JSON-RPC communication over stdio transparently.
    #
    # StdioConnectionParams tells ADK to spawn the MCP server as a
    # subprocess and communicate via stdin/stdout pipes. This is the
    # standard MCP transport for local servers.
    medminder_mcp = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="python",
                args=[_MCP_SERVER_SCRIPT],
                # Pass through the parent process's environment so the
                # MCP server inherits DB_PATH, API keys, and other config.
                # This avoids hardcoding configuration in multiple places.
                env={**os.environ},
            )
        )
    )

    # -------------------------------------------------------------------
    # Build the Schedule Agent
    # -------------------------------------------------------------------
    # The agent's instruction prompt is carefully crafted to:
    #   1. Define the agent's role and responsibilities clearly
    #   2. List specific tools and when to use them
    #   3. Set default behaviors (e.g., default user_id)
    #   4. Include medical disclaimers (required for health apps)
    #   5. Guide the LLM's response formatting
    schedule_agent = LlmAgent(
        name="ScheduleAgent",

        # Using gemini-2.0-flash for fast responses — medication schedule
        # queries should feel instant. Flash is sufficient since these
        # operations are mostly CRUD (no complex reasoning needed).
        model="gemini-2.0-flash",

        # Description is used by the ORCHESTRATOR to decide when to route
        # to this agent. It should clearly state what this agent handles
        # so the orchestrator's routing logic works accurately.
        description=(
            "Manages medication schedules, daily timelines, and reminders. "
            "Use this agent when the user wants to: see today's medication "
            "schedule, check what's due next, log that they took or missed "
            "a dose, add a new medication, remove a discontinued medication, "
            "or list all their current medications."
        ),

        # Instruction is the system prompt for THIS agent. It's only seen
        # when the orchestrator delegates to ScheduleAgent. The instruction
        # is detailed because the LLM needs to know exactly which tools
        # to call and with what parameters.
        instruction="""You are the Schedule Agent for MedMinder, a medication management assistant.

Your responsibilities:
1. Show users their daily medication schedule using get_todays_schedule
2. Help users log doses (taken, missed, late) using log_dose or log_missed_dose
3. Add new medications to their schedule using add_medication
4. Remove discontinued medications using remove_medication
5. List all current medications using list_medications

TOOL USAGE GUIDELINES:
━━━━━━━━━━━━━━━━━━━━━
• get_todays_schedule(user_id) — Call this FIRST when a user asks about their
  schedule, what to take today, or what's coming up next.

• log_dose(medication_id, status, notes) — Call when a user confirms they took
  a dose. Use status='taken' (default), 'missed', or 'late'. You need the
  medication_id, so call list_medications first if you don't have it.

• log_missed_dose(medication_id, reason) — Convenience tool for missed doses.
  Use when the user explicitly says they missed or forgot a medication.

• add_medication(user_id, name, dosage, frequency, times, notes) — Call when a
  user wants to add a new medication. Gather ALL required fields before calling:
    - name: Medication name (e.g., 'Lisinopril')
    - dosage: Amount with units (e.g., '10mg', '2 tablets')
    - frequency: How often (e.g., 'once daily', 'twice daily')
    - times: Comma-separated 24hr times (e.g., '08:00' or '08:00,20:00')
    - notes: Optional (e.g., 'take with food')

• remove_medication(medication_id) — Call when a user wants to stop tracking
  a medication. This is a soft delete — historical data is preserved.

• list_medications(user_id) — Call when a user asks what medications they're
  tracking, or when you need to find a medication_id for other operations.

FORMATTING RULES:
━━━━━━━━━━━━━━━━━
• When showing schedules, format times in a clear 12-hour format with AM/PM
• Use checkmarks (✅) for completed doses and circles (⭕) for pending ones
• Always show the medication name, dosage, and scheduled time together
• When showing adherence data, use percentages and simple visual indicators

DEFAULT BEHAVIORS:
━━━━━━━━━━━━━━━━━━
• Always use user_id 'default_user' unless the user specifies a different ID
• When a user says they 'took' a medication, immediately call log_dose
• When a user says they 'missed' or 'forgot', immediately call log_missed_dose
• If adding a medication and missing required info, ASK for it — don't guess

⚕️ MEDICAL DISCLAIMER:
Always remind users that this tool is for tracking purposes only and does
not constitute medical advice. Never advise users to change medication
dosages, skip doses, or alter their prescribed regimen. If a user asks
about changing their medication, recommend they consult their doctor.""",

        # Tools list — McpToolset provides all tools from the MCP server.
        # ADK will discover the available tools via MCP's tools/list method
        # when the agent is initialized.
        tools=[medminder_mcp],
    )

    logger.info("ScheduleAgent created successfully.")
    return schedule_agent
