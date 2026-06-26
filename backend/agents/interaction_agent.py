"""
Interaction Agent — Checks drug interactions and provides drug safety info.
===========================================================================

This agent is the safety-critical component of MedMinder. It connects to
multiple external MCP servers that provide drug interaction databases,
FDA drug information, and medical literature search capabilities.

Architecture & Design Decisions:
---------------------------------
1. **Multiple MCP servers**: Unlike the ScheduleAgent (which uses only our
   custom server), the InteractionAgent aggregates tools from THREE external
   MCP servers. This is a key demonstration of MCP's composability — the
   agent sees all tools as a flat list regardless of which server provides them.

2. **Graceful degradation**: External MCP servers require separate installation
   (pip install biomcp-python, npm install healthcare-mcp, etc.). Since users
   may not have all of them installed, each connection is wrapped in try/except.
   The agent works with whatever subset of servers is available, and warns
   about unavailable ones via logging.

3. **Safety-first instruction design**: Drug interactions can be life-threatening.
   The agent's instruction prompt emphasizes:
     - Always checking interactions when multiple drugs are mentioned
     - Using severity ratings (minor/moderate/major/contraindicated)
     - Including disclaimers on every interaction result
     - Recommending professional consultation for major interactions

4. **External MCP Server Details**:
   - **BioMCP**: Provides DDInter drug-drug interaction database and PubMed
     search. Install: `pip install biomcp-python` then `biomcp serve`
   - **drug-interaction-mcp**: Dedicated drug interaction checker with
     comprehensive database. Install: `pip install drug-interaction-mcp`
     then `uvx drug-interaction-mcp`
   - **healthcare-mcp-public**: FDA drug labels, ICD-10 codes, PubMed,
     and medical calculators. Install: `npm install -g healthcare-mcp`
     then `npx -y healthcare-mcp`

⚕️ MEDICAL DISCLAIMER:
  Drug interaction information provided by this agent is for EDUCATIONAL
  and INFORMATIONAL purposes only. It is sourced from third-party databases
  that may not be complete or current. ALWAYS consult a pharmacist or
  physician before combining medications. Missing interactions in this
  system does NOT mean two drugs are safe to combine.

Usage:
  from backend.agents.interaction_agent import create_interaction_agent
  agent = create_interaction_agent()
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
logger = logging.getLogger("medminder.agents.interaction")


def _create_biomcp_toolset() -> McpToolset | None:
    """Attempt to create a McpToolset for the BioMCP server.

    BioMCP provides access to:
      - DDInter: Drug-Drug Interaction database with severity ratings
      - PubMed: Medical literature search for evidence-based information

    Install: pip install biomcp-python
    Run:     biomcp serve

    Returns:
        McpToolset if connection params are valid, None if setup fails.
        Note: The actual connection is established lazily when the first
        tool call is made, not at creation time.
    """
    try:
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    # 'biomcp' is installed as a CLI entry point by
                    # pip install biomcp-python. The 'serve' subcommand
                    # starts the MCP server in stdio mode.
                    command="biomcp",
                    args=["serve"],
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "HOME": os.environ.get("HOME", "/tmp"),
                        "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", "/tmp/.cache"),
                    },
                ),
                timeout=60,
            )
        )
        logger.info("BioMCP toolset created successfully.")
        return toolset
    except Exception as e:
        # If biomcp isn't installed or configured, we log and continue.
        # The agent will still work with the other MCP servers.
        logger.warning(
            "BioMCP toolset unavailable (biomcp may not be installed): %s. "
            "Drug interaction data from DDInter and PubMed search will not "
            "be available. Install with: pip install biomcp-python",
            str(e),
        )
        return None


def _create_drug_interaction_toolset() -> McpToolset | None:
    """Attempt to create a McpToolset for the drug-interaction-mcp server.

    This dedicated interaction checker provides comprehensive drug-drug
    interaction data with clinical significance ratings and management
    recommendations.

    Install: pip install drug-interaction-mcp
    Run:     uvx drug-interaction-mcp

    Returns:
        McpToolset if connection params are valid, None if setup fails.
    """
    try:
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    # 'uvx' is the uv tool runner (like npx for Python).
                    # It runs the drug-interaction-mcp package directly
                    # without needing a separate install step.
                    command="uvx",
                    args=["drug-interaction-mcp"],
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "HOME": os.environ.get("HOME", "/tmp"),
                        "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", "/tmp/.cache"),
                    },
                ),
                timeout=60,
            )
        )
        logger.info("drug-interaction-mcp toolset created successfully.")
        return toolset
    except Exception as e:
        logger.warning(
            "drug-interaction-mcp toolset unavailable: %s. "
            "Dedicated drug interaction checking will not be available. "
            "Install with: pip install drug-interaction-mcp",
            str(e),
        )
        return None


def _create_healthcare_mcp_toolset() -> McpToolset | None:
    """Attempt to create a McpToolset for the healthcare-mcp-public server.

    healthcare-mcp-public provides access to:
      - FDA Drug Labels: Official drug information from openFDA
      - ICD-10 Codes: International Classification of Diseases lookup
      - PubMed: Medical literature search (complementary to BioMCP's)
      - Medical Calculators: BMI, eGFR, and other clinical calculators

    Install: npm install -g healthcare-mcp
    Run:     npx -y healthcare-mcp

    Returns:
        McpToolset if connection params are valid, None if setup fails.
    """
    try:
        toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    # 'npx -y' runs the package without prompting for
                    # installation confirmation. The '-y' flag is important
                    # for non-interactive execution in an agent context.
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
        logger.info("healthcare-mcp-public toolset created successfully.")
        return toolset
    except Exception as e:
        logger.warning(
            "healthcare-mcp-public toolset unavailable: %s. "
            "FDA drug info, ICD-10 codes, and medical calculators will not "
            "be available. Install with: npm install -g healthcare-mcp",
            str(e),
        )
        return None


def create_interaction_agent() -> LlmAgent:
    """Create and return the Interaction Agent with external MCP tools.

    This factory function builds the InteractionAgent by connecting to
    multiple external MCP servers. Each connection is attempted independently,
    so the agent works with whatever subset of servers is available.

    The agent's tool set may vary depending on which MCP servers are
    installed. At minimum, the agent can still provide general drug
    interaction guidance based on its training data, even if no external
    MCP servers are available.

    Returns:
        LlmAgent: A fully configured Interaction Agent ready to be used
                  as a sub-agent in the MedMinder orchestrator.
    """
    logger.info("Creating InteractionAgent — connecting to external MCP servers...")

    # -------------------------------------------------------------------
    # Collect available MCP toolsets
    # -------------------------------------------------------------------
    # Each factory function returns None if the server isn't available.
    # We filter out None values to get only the working toolsets.
    # This graceful degradation pattern ensures the agent always starts,
    # even if external dependencies are missing.
    available_toolsets: list[McpToolset] = []
    unavailable_servers: list[str] = []

    # Attempt BioMCP connection (DDInter interactions + PubMed)
    biomcp = _create_biomcp_toolset()
    if biomcp:
        available_toolsets.append(biomcp)
    else:
        unavailable_servers.append("BioMCP (DDInter/PubMed)")

    # Attempt drug-interaction-mcp connection
    drug_interaction = _create_drug_interaction_toolset()
    if drug_interaction:
        available_toolsets.append(drug_interaction)
    else:
        unavailable_servers.append("drug-interaction-mcp")

    # Attempt healthcare-mcp-public connection (FDA/ICD-10/PubMed)
    healthcare = _create_healthcare_mcp_toolset()
    if healthcare:
        available_toolsets.append(healthcare)
    else:
        unavailable_servers.append("healthcare-mcp-public (FDA/ICD-10)")

    # Log a summary of available vs unavailable servers
    if available_toolsets:
        logger.info(
            "InteractionAgent has %d MCP toolset(s) available.",
            len(available_toolsets),
        )
    else:
        logger.warning(
            "InteractionAgent has NO external MCP servers available. "
            "The agent will rely on its training data for interaction info. "
            "For full functionality, install: biomcp-python, "
            "drug-interaction-mcp, healthcare-mcp"
        )

    if unavailable_servers:
        logger.info(
            "Unavailable MCP servers: %s", ", ".join(unavailable_servers)
        )

    # -------------------------------------------------------------------
    # Build the Interaction Agent
    # -------------------------------------------------------------------
    interaction_agent = LlmAgent(
        name="InteractionAgent",

        # Using gemini-2.5-flash — interaction checks need to be fast
        # because they're often triggered as safety checks during other
        # operations (e.g., when adding a new medication).
        model="gemini-2.5-flash",

        # Description for the orchestrator's routing logic.
        # Keywords here help the orchestrator recognize interaction-related
        # queries: "interactions", "safety", "side effects", "FDA", etc.
        description=(
            "Checks drug-drug interactions, provides medication safety alerts, "
            "looks up FDA drug information, searches medical literature, and "
            "answers questions about drug side effects. Use this agent when the "
            "user asks about: whether two drugs interact, medication safety, "
            "side effects, FDA drug information, or drug research."
        ),

        # Detailed instruction prompt for the interaction-checking LLM.
        # This is the most safety-critical prompt in the entire system.
        instruction="""You are the Interaction Agent for MedMinder, specializing in drug safety.

Your PRIMARY responsibility is protecting users from dangerous drug interactions.

CORE CAPABILITIES:
━━━━━━━━━━━━━━━━━━
1. **Drug Interaction Checking**: When a user mentions two or more drugs,
   ALWAYS check for interactions using your available tools.

2. **FDA Drug Information**: Look up official drug labels, warnings, and
   approved uses from the FDA database.

3. **Medical Literature Search**: Search PubMed for recent research on
   drug safety, interactions, and side effects.

4. **Side Effect Information**: Provide known side effects categorized by
   frequency (common, uncommon, rare, serious).

INTERACTION SEVERITY LEVELS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Always categorize interactions by severity and use appropriate visual indicators:

🟢 MINOR — Minimal clinical significance. Monitor but usually safe.
   Action: Inform the user, no immediate action needed.

🟡 MODERATE — May require dosage adjustment or monitoring.
   Action: Recommend discussing with pharmacist or doctor at next visit.

🔴 MAJOR — Potentially dangerous combination requiring immediate attention.
   Action: Strongly recommend contacting their healthcare provider BEFORE
   taking the medications together.

⛔ CONTRAINDICATED — Drugs should NEVER be taken together.
   Action: URGENT warning. Recommend contacting their doctor or pharmacist
   IMMEDIATELY. Do not downplay the severity.

TOOL USAGE PRIORITY:
━━━━━━━━━━━━━━━━━━━━
When checking interactions, try tools in this order (use whatever is available):
1. Drug-interaction-mcp tools (most comprehensive interaction data)
2. BioMCP DDInter tools (drug-drug interaction database)
3. Healthcare-mcp FDA tools (official drug label information)
4. BioMCP PubMed search (research literature as backup)

If NO external tools are available, provide interaction information based on
your training data, but CLEARLY STATE that the information could not be
verified against a live database and recommend professional verification.

RESPONSE FORMATTING:
━━━━━━━━━━━━━━━━━━━━
For each interaction found, always include:
- The two drugs involved
- Severity level with color indicator
- Clinical description of the interaction
- Mechanism of action (if known)
- Recommended action for the patient
- Source of the information

PROACTIVE SAFETY:
━━━━━━━━━━━━━━━━━
- If a user mentions adding a new medication, PROACTIVELY offer to check
  interactions with their current medications.
- If you detect a potentially dangerous combination, lead with the warning
  BEFORE providing other information.
- For MAJOR or CONTRAINDICATED interactions, use bold formatting and clear
  visual indicators to ensure the warning is not overlooked.

⚕️ MEDICAL DISCLAIMER:
This interaction information is sourced from third-party databases and
may not be complete or fully current. A clean interaction check does NOT
guarantee safety — there may be interactions not yet in the database.

ALWAYS recommend:
- Consulting a pharmacist (they are interaction specialists)
- Informing all prescribers about all medications being taken
- Reporting any new or unusual symptoms when combining medications

Never tell a user it is "safe" to combine medications — instead, say
"no known interactions were found" and recommend professional verification.""",

        # Tools list — contains whatever MCP toolsets were successfully created.
        # If empty, the agent still works using its training knowledge.
        tools=available_toolsets,
    )

    logger.info(
        "InteractionAgent created with %d tool source(s).",
        len(available_toolsets),
    )
    return interaction_agent
