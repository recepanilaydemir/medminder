"""
MedMinder Orchestrator Agent — The root agent that coordinates all sub-agents.
===============================================================================

This is the TOP-LEVEL agent in the MedMinder multi-agent hierarchy. It serves
as the user's primary interface and routes requests to the appropriate
specialist sub-agent based on the user's intent.

Architecture & Design Decisions:
---------------------------------
1. **LLM-based routing via sub_agents**: Google ADK's LlmAgent supports a
   `sub_agents` parameter. When the orchestrator receives a request, the LLM
   reads each sub-agent's `description` field and decides whether to:
     - Handle the request directly (greetings, general questions)
     - Delegate to ScheduleAgent (medication timing, dose logging)
     - Delegate to InteractionAgent (drug safety, interactions)
     - Delegate to HealthAgent (symptoms, reports, adherence)

   This is more flexible than rule-based routing (regex, keyword matching)
   because the LLM understands intent, synonyms, and context. A user saying
   "I forgot my pills" routes to ScheduleAgent even without the word "schedule".

2. **Orchestrator as personality layer**: The orchestrator's instruction defines
   MedMinder's personality (warm, empathetic, encouraging) while the sub-agents
   focus on technical capabilities. This separation means we can adjust the
   user experience without touching the specialist logic.

3. **Factory function pattern**: Like all agents, the orchestrator uses a factory
   function (`create_root_agent`) rather than a module-level instance. This:
     - Avoids import-time side effects (MCP connections, subprocess spawning)
     - Makes the system testable (mock the factory in tests)
     - Ensures clean lifecycle management

4. **Sub-agent independence**: Each sub-agent is fully self-contained with its
   own MCP connections and instruction set. The orchestrator doesn't need to
   know about MCP servers, database schemas, or tool implementations — it only
   needs to know WHEN to delegate WHERE.

Multi-Agent Flow:
  ┌──────────┐     intent      ┌──────────────┐
  │   User   │ ───────────────►│  Orchestrator │
  └──────────┘                 │  (MedMinder)  │
                               └──────┬───────┘
                                      │ routes to...
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │ ScheduleAgent│  │ Interaction  │  │  HealthAgent │
            │              │  │    Agent     │  │              │
            │ • Schedules  │  │ • Drug-Drug  │  │ • Symptoms   │
            │ • Dose logs  │  │   checks     │  │ • Adherence  │
            │ • Add/Remove │  │ • FDA info   │  │ • Reports    │
            │   meds       │  │ • PubMed     │  │ • Dr Summary │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                   │                 │                  │
                   ▼                 ▼                  ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │  MedMinder   │  │   BioMCP     │  │  MedMinder   │
            │  MCP Server  │  │   Drug-Int   │  │  MCP Server  │
            │              │  │   Healthcare │  │  + Healthcare│
            └──────────────┘  └──────────────┘  └──────────────┘

⚕️ MEDICAL DISCLAIMER:
  MedMinder is an AI-powered medication management ASSISTANT designed for
  informational and tracking purposes only. It is NOT a medical device,
  NOT FDA approved, and NOT a substitute for professional medical advice,
  diagnosis, or treatment. Always seek the advice of your physician or
  other qualified health provider with any questions you may have regarding
  a medical condition or medication regimen.

Usage:
  from backend.agents.orchestrator import create_root_agent
  root = create_root_agent()

  # Or via the package-level export:
  from backend.agents import create_root_agent
  root = create_root_agent()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent

# Import sub-agent factory functions
# These are relative imports within the agents package
from .schedule_agent import create_schedule_agent
from .interaction_agent import create_interaction_agent
from .health_agent import create_health_agent

if TYPE_CHECKING:
    pass  # Reserved for future type-only imports

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("medminder.agents.orchestrator")


def create_root_agent() -> LlmAgent:
    """Create the root MedMinder agent with all sub-agents.

    This is the main entry point for the entire MedMinder agent system.
    It creates all three specialist sub-agents and composes them under
    a single orchestrator agent.

    The creation order doesn't matter for functionality, but we create
    them in logical order for readability:
      1. ScheduleAgent (most commonly used)
      2. InteractionAgent (safety-critical)
      3. HealthAgent (reporting and monitoring)

    Returns:
        LlmAgent: The root orchestrator agent with all sub-agents attached.
                  This agent is ready to be used with ADK's runner, web UI,
                  or any other ADK-compatible interface.

    Example:
        >>> root = create_root_agent()
        >>> # Use with ADK's InMemoryRunner for testing:
        >>> from google.adk.runners import InMemoryRunner
        >>> runner = InMemoryRunner(agent=root)
    """
    logger.info("=" * 60)
    logger.info("Initializing MedMinder Multi-Agent System")
    logger.info("=" * 60)

    # -------------------------------------------------------------------
    # Create specialist sub-agents
    # -------------------------------------------------------------------
    # Each factory function handles its own MCP connections and error handling.
    # If an external MCP server isn't available, the sub-agent still works
    # with reduced functionality (graceful degradation).

    logger.info("[1/3] Creating ScheduleAgent...")
    schedule = create_schedule_agent()

    logger.info("[2/3] Creating InteractionAgent...")
    interaction = create_interaction_agent()

    logger.info("[3/3] Creating HealthAgent...")
    health = create_health_agent()

    # -------------------------------------------------------------------
    # Build the root orchestrator agent
    # -------------------------------------------------------------------
    # The orchestrator's instruction is the MOST IMPORTANT prompt in the
    # system because it controls:
    #   - How the user perceives MedMinder's personality
    #   - Whether requests get routed to the correct sub-agent
    #   - How edge cases (ambiguous requests, emergencies) are handled
    root_agent = LlmAgent(
        name="MedMinder",

        # The orchestrator also uses flash for fast routing decisions.
        # Routing doesn't require deep reasoning — it's mostly intent
        # classification based on the sub-agent descriptions.
        model="gemini-2.0-flash",

        # Top-level description — used if this agent is itself a sub-agent
        # in a larger system (future-proofing for multi-app architectures).
        description=(
            "MedMinder — Your AI Medication Management Assistant. "
            "Helps users manage medications, check drug interactions, "
            "track symptoms, and generate health reports."
        ),

        # The orchestrator's instruction defines MedMinder's personality
        # and routing logic. It references sub-agents by name so the LLM
        # knows exactly which agent handles what.
        instruction="""You are MedMinder, a friendly and helpful AI medication management assistant.

You help users manage their medications safely by coordinating three specialist agents:

1. **ScheduleAgent**: Handles medication schedules, dose logging, adding/removing meds
   → Route here when users ask about:
     • Their daily medication schedule ("What do I take today?")
     • Logging that they took or missed a dose ("I just took my Lisinopril")
     • Adding a new medication ("I need to add a new prescription")
     • Removing a medication ("I stopped taking Metformin")
     • Listing their current medications ("What medications am I on?")

2. **InteractionAgent**: Checks drug interactions, provides drug safety info
   → Route here when users ask about:
     • Drug-drug interactions ("Can I take ibuprofen with aspirin?")
     • Medication side effects ("What are the side effects of Lisinopril?")
     • FDA drug information ("Tell me about Metformin")
     • Drug safety concerns ("Is it safe to take these together?")
     • Medical research on medications ("Latest research on statins")

3. **HealthAgent**: Tracks symptoms, generates reports, monitors adherence
   → Route here when users ask about:
     • Reporting symptoms ("I have a headache" or "I feel dizzy")
     • Medication adherence ("How well have I been taking my meds?")
     • Doctor preparation ("Generate a report for my doctor appointment")
     • Symptom history ("Show me my recent symptoms")
     • Health tracking and trends ("How's my overall health tracking?")

ROUTING GUIDELINES:
━━━━━━━━━━━━━━━━━━
• Analyze the user's intent carefully before routing
• If a request involves MULTIPLE agents (e.g., "Add this medication and check
  for interactions"), handle them sequentially — first route to one agent,
  then the other
• For ambiguous requests, ask a clarifying question rather than guessing
• NEVER fabricate medication data — always delegate to the appropriate agent

PERSONALITY & TONE:
━━━━━━━━━━━━━━━━━━
• Be warm, empathetic, and encouraging
• Celebrate medication adherence wins ("Great job staying on track! 🎉")
• Be gentle about missed doses (no guilt-tripping)
• Use simple, non-technical language unless the user prefers otherwise
• Add appropriate emoji to make responses feel friendly but professional

HANDLE DIRECTLY (without delegating):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Greetings and small talk ("Hello!", "How are you?")
• Explaining what MedMinder can do ("What can you help me with?")
• General encouragement and motivation
• Answering questions about the app itself

EMERGENCY PROTOCOL:
━━━━━━━━━━━━━━━━━━
If a user reports ANY of the following, respond with IMMEDIATE urgency:
  🚨 Severity 5 symptoms → Route to HealthAgent, but ALSO tell the user
     to call emergency services (911) RIGHT AWAY
  🚨 Mentions of overdose → Advise calling Poison Control (1-800-222-1222)
     or emergency services immediately
  🚨 Severe allergic reaction → Advise calling emergency services immediately

For emergencies, the safety message comes FIRST, before any data logging.

PROACTIVE SUGGESTIONS:
━━━━━━━━━━━━━━━━━━━━━
After completing a user's request, offer relevant follow-ups:
  • After logging a dose → "Would you like to see your schedule for today?"
  • After adding a medication → "Want me to check for interactions with your
    other medications?"
  • After reporting a symptom → "Would you like me to note which medication
    might be related?"
  • After showing adherence → "Would you like to generate a report for your
    doctor?"

⚕️ IMPORTANT MEDICAL DISCLAIMER:
You are NOT a doctor, pharmacist, or medical professional. MedMinder is an
AI assistant for medication TRACKING and INFORMATION purposes only.

ALWAYS remind users to:
  • Consult their healthcare provider for medical decisions
  • Not change medication dosages without professional guidance
  • Seek emergency care for severe symptoms
  • Verify drug interaction information with a pharmacist

NEVER:
  • Diagnose medical conditions
  • Recommend specific medications or dosages
  • Advise stopping or changing prescribed medications
  • Downplay potentially serious symptoms or interactions""",

        # Sub-agents — ADK reads each agent's `description` field to
        # understand what it handles, then the LLM uses those descriptions
        # for routing decisions.
        sub_agents=[schedule, interaction, health],
    )

    logger.info("=" * 60)
    logger.info("MedMinder Multi-Agent System initialized successfully!")
    logger.info("  Root agent: %s", root_agent.name)
    logger.info("  Sub-agents: %s", [a.name for a in root_agent.sub_agents])
    logger.info("=" * 60)

    return root_agent
