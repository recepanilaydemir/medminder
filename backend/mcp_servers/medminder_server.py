"""
MedMinder MCP Server
====================

A custom Model Context Protocol (MCP) server that exposes the MedMinder
medication tracking database as a set of tools accessible to LLM agents.

Why MCP?
--------
MCP (Model Context Protocol) is an open standard that allows LLMs to
interact with external systems through a well-defined tool interface.
By building MedMinder as an MCP server, we enable ANY MCP-compatible
LLM client (Claude, Gemini, etc.) to:
  - Add/remove medications for a patient
  - Log doses and symptoms
  - Generate adherence reports
  - Create doctor-ready summaries

This is the CORE CAPSTONE DELIVERABLE — it demonstrates the ability to
design and implement a production-quality MCP server from scratch.

Architecture:
  ┌─────────────┐    stdio/SSE    ┌──────────────────┐    aiosqlite    ┌──────────┐
  │  LLM Client │ ◄────────────► │  MedMinder MCP   │ ◄────────────► │  SQLite  │
  │  (Claude)   │                │  Server (FastMCP) │                │    DB    │
  └─────────────┘                └──────────────────┘                └──────────┘

Design Decisions:
  - **FastMCP framework**: Provides automatic JSON Schema generation from
    Python type hints, built-in error handling, and stdio transport — all
    with minimal boilerplate. This lets us focus on business logic.
  - **Thin wrapper pattern**: Each MCP tool is a thin async function that
    delegates to MedMinderDB methods. This separation means the database
    layer can be tested independently and reused outside MCP.
  - **String returns**: All tools return JSON strings rather than complex
    objects. MCP tool results must be serializable text that the LLM can
    parse. We use json.dumps() with indentation for LLM readability.
  - **Comprehensive docstrings**: FastMCP uses function docstrings as tool
    descriptions during MCP tool discovery. Well-written docstrings directly
    improve how effectively an LLM can use each tool.
  - **Environment-configurable DB path**: The database file location can be
    set via MEDMINDER_DB_PATH env var, enabling flexible deployment.

⚕️ MEDICAL DISCLAIMER:
  This MCP server provides medication tracking tools for INFORMATIONAL
  and EDUCATIONAL purposes only. It is NOT a medical device, NOT FDA
  approved, and NOT a substitute for professional medical advice.
  All data is self-reported and should be verified by a healthcare
  professional before making any medical decisions.

Usage:
  # Run directly (stdio transport for MCP):
  python -m backend.mcp_servers.medminder_server

  # Or in MCP client configuration (e.g., Claude Desktop):
  {
    "mcpServers": {
      "medminder": {
        "command": "python",
        "args": ["-m", "backend.mcp_servers.medminder_server"],
        "cwd": "/path/to/KaggleCapstone"
      }
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Import the database layer
# ---------------------------------------------------------------------------
# We add the project root to sys.path so the backend package can be resolved
# when running this file directly (python -m or python medminder_server.py).
# This is a common pattern for MCP servers that need to be run as standalone
# scripts while still importing from a package structure.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.db.database import MedMinderDB  # noqa: E402

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
# Log to stderr so logs don't interfere with MCP's stdio transport.
# MCP uses stdout for JSON-RPC messages, so ANY print() or stdout output
# would corrupt the protocol. This is a critical detail for MCP servers.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("medminder.mcp")

# ---------------------------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------------------------
# The DB path is configurable via environment variable for flexibility.
# Default: 'medminder.db' in the project root directory.
# This allows different deployments (dev, test, prod) to use different DBs.
DB_PATH = os.environ.get("MEDMINDER_DB_PATH", os.path.join(_project_root, "medminder.db"))
db = MedMinderDB(db_path=DB_PATH)

# ---------------------------------------------------------------------------
# MCP Server Setup
# ---------------------------------------------------------------------------
# FastMCP creates an MCP-compliant server with automatic:
#   - JSON Schema generation from Python type hints
#   - Tool discovery and listing
#   - Error handling and response formatting
#   - stdio transport (default) for LLM client communication
#
# The server name "MedMinder" appears in MCP tool discovery responses,
# helping the LLM understand what this server is about.
mcp = FastMCP("MedMinder")

# We track whether the DB has been initialized to avoid redundant init calls.
# This flag is checked in _ensure_db() which is called before every tool.
_db_initialized = False


async def _ensure_db() -> None:
    """Lazily initialize the database on first tool call.

    Why lazy initialization?
      - FastMCP doesn't provide a clean startup hook for async init
      - We can't call `await db.init_db()` at module level (no event loop yet)
      - Lazy init on first tool call is simple and reliable

    The _db_initialized flag ensures init_db() runs exactly once, even if
    multiple tool calls arrive concurrently (though MCP typically processes
    requests sequentially over stdio).
    """
    global _db_initialized
    if not _db_initialized:
        logger.info("Initializing MedMinder database at: %s", DB_PATH)
        await db.init_db()
        _db_initialized = True
        logger.info("Database initialized successfully.")


# ===========================================================================
#  MCP TOOLS — Each function below is exposed as an MCP tool
# ===========================================================================
# IMPORTANT: The docstrings below serve DOUBLE DUTY:
#   1. Standard Python documentation
#   2. MCP tool descriptions shown to the LLM during tool discovery
#
# The LLM reads these descriptions to decide WHEN and HOW to call each tool.
# Clear, detailed docstrings = better LLM tool usage = better user experience.
# ===========================================================================


@mcp.tool()
async def add_medication(
    user_id: str,
    name: str,
    dosage: str,
    frequency: str,
    times: str,
    notes: str = "",
    confirmed: bool = False,
) -> str:
    """Add a new medication to a user's tracking regimen.

    ⚠️ SAFETY: This tool automatically performs TWO safety checks before adding:
      1. DUPLICATE CHECK — scans existing medications for the same name/times
      2. FDA DOSE VALIDATION — queries the openFDA API for standard dosage info

    If either check raises concerns, the tool returns a WARNING response with
    'requires_confirmation': true. The agent MUST show the warnings to the user
    and ask for confirmation. Then call this tool again with confirmed=true.

    Args:
        user_id: Unique identifier for the user (e.g., 'default_user').
        name: Medication name (e.g., 'Lisinopril', 'Metformin').
        dosage: Dosage with units (e.g., '10mg', '500mg', '2 tablets').
        frequency: How often (e.g., 'once daily', 'twice daily').
        times: Comma-separated 24hr times (e.g., '08:00' or '08:00,20:00').
        notes: Optional notes (e.g., 'take with food').
        confirmed: Set to true ONLY after the user has seen and acknowledged
                   any warnings. Do NOT set this to true on the first call.

    Returns:
        JSON with either:
        - 'requires_confirmation': true + warnings (if issues found)
        - 'status': 'success' + medication data (if clean or confirmed)
    """
    await _ensure_db()
    try:
        times_list = [t.strip() for t in times.split(",")]
        warnings = []

        # ─── SAFETY CHECK 1: Duplicate detection ─────────────────────
        if not confirmed:
            existing = await db.list_medications(user_id)
            for med in existing:
                if med.name.lower() == name.lower():
                    existing_times = ",".join(med.times) if med.times else "unknown"
                    requested_times = ",".join(times_list)
                    if existing_times == requested_times:
                        warnings.append({
                            "type": "duplicate_exact",
                            "message": (
                                f"⚠️ DUPLICATE: You already have {med.name} "
                                f"({med.dosage}) scheduled at {existing_times}. "
                                f"Adding this would create an identical duplicate."
                            ),
                        })
                    else:
                        warnings.append({
                            "type": "duplicate_different_time",
                            "message": (
                                f"📋 NOTE: You already have {med.name} "
                                f"({med.dosage}) at {existing_times}. "
                                f"You're adding a new schedule at {requested_times}."
                            ),
                        })
                elif med.name.lower() in name.lower() or name.lower() in med.name.lower():
                    warnings.append({
                        "type": "similar_name",
                        "message": (
                            f"🔍 SIMILAR: You have '{med.name}' — is '{name}' "
                            f"a different formulation or did you mean to update "
                            f"the existing one?"
                        ),
                    })

        # ─── SAFETY CHECK 2: FDA dose validation ─────────────────────
        if not confirmed:
            import urllib.request
            import urllib.parse
            import urllib.error

            try:
                query = urllib.parse.quote(name)
                url = (
                    f"https://api.fda.gov/drug/label.json"
                    f"?search=(openfda.brand_name:{query}+openfda.generic_name:{query})"
                    f"&limit=1"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "MedMinder/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    fda_data = json.loads(resp.read().decode())

                if fda_data.get("results"):
                    result = fda_data["results"][0]
                    dosage_info = ""
                    if result.get("dosage_and_administration"):
                        dosage_info = result["dosage_and_administration"][0][:800]

                    brand = (result.get("openfda", {}).get("brand_name", [None])[0]
                             if result.get("openfda") else None)
                    generic = (result.get("openfda", {}).get("generic_name", [None])[0]
                               if result.get("openfda") else None)

                    warnings.append({
                        "type": "fda_info",
                        "severity": "info",
                        "message": (
                            f"📋 FDA Drug Label ({brand or generic or name}):\n"
                            f"{dosage_info}"
                        ),
                        "source": "openFDA Drug Label API (api.fda.gov)",
                    })
                else:
                    warnings.append({
                        "type": "fda_not_found",
                        "severity": "info",
                        "message": f"No FDA drug label found for '{name}'. Verify the name and dosage.",
                    })
            except Exception as e:
                logger.warning("FDA lookup failed for '%s': %s", name, str(e))
                warnings.append({
                    "type": "fda_error",
                    "severity": "info",
                    "message": f"Could not verify dosage with FDA database. Proceeding with your input.",
                })

        # ─── Return warnings if any found (and not yet confirmed) ────
        if warnings and not confirmed:
            logger.info(
                "Tool add_medication: %d warning(s) for '%s' — requiring confirmation",
                len(warnings), name,
            )
            return json.dumps({
                "status": "requires_confirmation",
                "message": (
                    f"Before adding {name} ({dosage}, {frequency} at {times}), "
                    f"please review the following and confirm with the user:"
                ),
                "warnings": warnings,
                "action_needed": (
                    "Show ALL warnings to the user. Ask if they want to proceed. "
                    "If they confirm, call add_medication again with confirmed=true."
                ),
                "medication_preview": {
                    "name": name, "dosage": dosage,
                    "frequency": frequency, "times": times,
                },
            }, indent=2)

        # ─── All clear (or confirmed): actually add the medication ───
        medication = await db.add_medication(
            user_id=user_id,
            name=name,
            dosage=dosage,
            frequency=frequency,
            times=times_list,
            notes=notes if notes else None,
        )

        logger.info("Tool add_medication: Added '%s' for user '%s'", name, user_id)

        return json.dumps(
            {
                "status": "success",
                "message": f"Successfully added {name} ({dosage}) to your medications.",
                "medication": medication.model_dump(),
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool add_medication failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to add medication: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def remove_medication(medication_id: str) -> str:
    """Remove (deactivate) a medication from tracking.

    This performs a SOFT DELETE — the medication is marked as inactive but
    its historical dose data is preserved for adherence reporting. Use this
    when a user stops taking a medication or a doctor discontinues it.

    To find the medication_id, first use list_medications to see all active
    medications and their IDs.

    ⚕️ MEDICAL DISCLAIMER: Removing a medication from this tracker does NOT
    mean the patient should stop taking it. Always follow the prescriber's
    instructions regarding medication changes.

    Args:
        medication_id: The unique UUID of the medication to deactivate.
                       Get this from list_medications.

    Returns:
        JSON string confirming whether the medication was successfully
        deactivated or if it was not found.
    """
    await _ensure_db()
    try:
        success = await db.remove_medication(medication_id)

        if success:
            return json.dumps(
                {
                    "status": "success",
                    "message": "Medication has been deactivated. Historical data preserved.",
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "status": "not_found",
                    "message": (
                        f"No active medication found with ID '{medication_id}'. "
                        "It may already be removed or the ID may be incorrect."
                    ),
                },
                indent=2,
            )
    except Exception as e:
        logger.error("Tool remove_medication failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to remove medication: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def list_medications(user_id: str) -> str:
    """List all active medications for a user.

    Returns a comprehensive list of all medications currently being tracked,
    including dosage, frequency, scheduled times, and any notes. Use this
    tool to:
      - Show the user their current medication list
      - Find a medication_id before logging a dose or removing a medication
      - Verify medication details before generating reports

    Args:
        user_id: The unique identifier of the user whose medications to list.

    Returns:
        JSON string containing an array of medication objects. Each object
        includes: id, name, dosage, frequency, times, start_date, notes.
        Returns an empty array if the user has no active medications.
    """
    await _ensure_db()
    try:
        medications = await db.list_medications(user_id)

        med_list = [med.model_dump() for med in medications]

        return json.dumps(
            {
                "status": "success",
                "count": len(med_list),
                "medications": med_list,
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool list_medications failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to list medications: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def log_dose(
    medication_id: str,
    status: str = "taken",
    notes: str = "",
) -> str:
    """Log a dose event for a medication (taken, missed, or late).

    Call this tool when a user confirms they've taken a dose, reports a
    missed dose, or acknowledges a late dose. Each call creates a
    timestamped record used for adherence tracking.

    Dose statuses:
      - 'taken': The medication was taken at or near the scheduled time
      - 'missed': The medication was not taken at all
      - 'late': The medication was taken but significantly after the
                scheduled time

    ⚕️ MEDICAL DISCLAIMER: Dose logging is self-reported. If a user is
    unsure whether they took a dose, advise them to consult their
    healthcare provider rather than taking an extra dose.

    Args:
        medication_id: UUID of the medication. Get this from list_medications.
        status: One of 'taken', 'missed', or 'late'. Defaults to 'taken'.
        notes: Optional notes about the dose (e.g., 'took 30 minutes late',
               'experienced nausea after taking').

    Returns:
        JSON string confirming the dose was logged with timestamp.

    Example:
        log_dose('abc-123-def', 'taken', 'Took with breakfast')
    """
    await _ensure_db()

    # Validate status before attempting database operation
    valid_statuses = {"taken", "missed", "late"}
    if status not in valid_statuses:
        return json.dumps(
            {
                "status": "error",
                "message": (
                    f"Invalid dose status '{status}'. "
                    f"Must be one of: {', '.join(sorted(valid_statuses))}"
                ),
            },
            indent=2,
        )

    try:
        dose_log = await db.log_dose(
            medication_id=medication_id,
            status=status,
            notes=notes if notes else None,
        )

        # Craft a user-friendly confirmation message
        status_messages = {
            "taken": "✅ Dose recorded as taken.",
            "missed": "⚠️ Missed dose has been recorded.",
            "late": "🕐 Late dose has been recorded.",
        }

        return json.dumps(
            {
                "status": "success",
                "message": status_messages[status],
                "dose_log": dose_log.model_dump(),
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool log_dose failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to log dose: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def log_missed_dose(medication_id: str, reason: str = "") -> str:
    """Convenience tool to log a missed dose with an optional reason.

    This is a shorthand for log_dose(medication_id, status='missed').
    It's provided as a separate tool because LLMs tend to use explicit,
    named tools more reliably than passing specific parameter values.

    Tracking missed dose reasons helps identify adherence barriers:
      - 'forgot' → might benefit from reminders
      - 'side effects' → may need medication adjustment
      - 'ran out' → prescription refill needed
      - 'felt fine without it' → patient education opportunity

    ⚕️ MEDICAL DISCLAIMER: Missing medication doses can have serious health
    consequences. If doses are frequently missed, the patient should discuss
    this with their healthcare provider.

    Args:
        medication_id: UUID of the medication that was missed.
        reason: Optional reason why the dose was missed (e.g., 'forgot',
                'ran out of medication', 'side effects').

    Returns:
        JSON string confirming the missed dose was logged.
    """
    await _ensure_db()
    try:
        # Delegate to the core log_dose method with status='missed'
        notes = f"Reason: {reason}" if reason else None
        dose_log = await db.log_dose(
            medication_id=medication_id,
            status="missed",
            notes=notes,
        )

        return json.dumps(
            {
                "status": "success",
                "message": (
                    "⚠️ Missed dose has been recorded."
                    + (f" Reason: {reason}" if reason else "")
                ),
                "dose_log": dose_log.model_dump(),
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool log_missed_dose failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to log missed dose: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def log_symptom(
    user_id: str,
    description: str,
    severity: int,
    related_medication: str = "",
) -> str:
    """Log a symptom or side effect experienced by the user.

    Use this tool when a user reports any symptom, whether or not it's
    believed to be medication-related. Symptom tracking enables:
      - Side effect monitoring and correlation with medications
      - Providing doctors with a comprehensive symptom timeline
      - Identifying patterns (e.g., headaches always after a specific med)

    Severity scale:
      1 = Minimal   — barely noticeable, no impact on daily life
      2 = Mild      — noticeable but doesn't affect activities
      3 = Moderate  — affects some daily activities
      4 = Severe    — significantly limits daily activities
      5 = Emergency — requires immediate medical attention

    ⚕️ MEDICAL DISCLAIMER: If severity is 4 or 5, strongly recommend
    the user contact their healthcare provider immediately. For severity 5,
    advise calling emergency services.

    Args:
        user_id: The unique identifier of the user reporting the symptom.
        description: Clear description of the symptom (e.g., 'headache',
                     'dizziness when standing', 'upset stomach after eating').
        severity: Integer from 1 to 5 indicating symptom severity.
        related_medication: Optional name of suspected medication causing
                           the symptom. Leave empty if unknown.

    Returns:
        JSON string confirming the symptom was logged, with a warning
        message for high-severity symptoms.
    """
    await _ensure_db()

    # Validate severity range
    if not 1 <= severity <= 5:
        return json.dumps(
            {
                "status": "error",
                "message": f"Severity must be between 1 and 5, got {severity}.",
            },
            indent=2,
        )

    try:
        symptom = await db.log_symptom(
            user_id=user_id,
            description=description,
            severity=severity,
            related_medication=related_medication if related_medication else None,
        )

        # Build severity-appropriate response message
        severity_labels = {
            1: "Minimal",
            2: "Mild",
            3: "Moderate",
            4: "Severe",
            5: "Emergency",
        }
        label = severity_labels.get(severity, "Unknown")

        # Add urgency warnings for high-severity symptoms
        warning = ""
        if severity >= 4:
            warning = (
                "\n\n⚠️ HIGH SEVERITY ALERT: This symptom has been rated as "
                f"'{label}'. Please contact your healthcare provider as soon "
                "as possible."
            )
        if severity == 5:
            warning = (
                "\n\n🚨 EMERGENCY SEVERITY: This symptom requires immediate "
                "medical attention. Please call emergency services or go to "
                "the nearest emergency room."
            )

        return json.dumps(
            {
                "status": "success",
                "message": f"Symptom logged: {description} (Severity: {label}){warning}",
                "symptom": symptom.model_dump(),
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool log_symptom failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to log symptom: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def get_adherence_report(user_id: str, days: int = 30) -> str:
    """Generate a medication adherence report for a specified time period.

    This tool analyzes dose logging data to calculate adherence statistics
    for each active medication. The report includes:
      - Total expected doses in the period
      - Number of doses taken on time, missed, and taken late
      - Adherence percentage (taken / total × 100)

    Use this tool when:
      - A user asks about their medication adherence
      - Preparing for a doctor's appointment
      - Monitoring adherence trends over time

    Adherence interpretation guidelines (per WHO):
      - ≥ 80% = Good adherence
      - 50-79% = Moderate adherence — may need intervention
      - < 50% = Poor adherence — urgent intervention needed

    ⚕️ MEDICAL DISCLAIMER: Adherence percentages are based on self-reported
    data and may not reflect actual medication intake. Low adherence should
    be discussed with a healthcare provider.

    Args:
        user_id: The unique identifier of the user.
        days: Number of days to look back for the report (default: 30).
              Common values: 7 (weekly), 30 (monthly), 90 (quarterly).

    Returns:
        JSON string containing adherence statistics for each active
        medication, including percentage and dose counts.
    """
    await _ensure_db()
    try:
        reports = await db.get_adherence_report(user_id, days)

        report_data = [r.model_dump() for r in reports]

        # Calculate overall adherence across all medications
        total_all = sum(r.total_doses for r in reports)
        taken_all = sum(r.taken for r in reports)
        overall_pct = (taken_all / total_all * 100.0) if total_all > 0 else 0.0

        return json.dumps(
            {
                "status": "success",
                "period_days": days,
                "overall_adherence_percentage": round(overall_pct, 1),
                "medication_count": len(report_data),
                "reports": report_data,
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool get_adherence_report failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to generate adherence report: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def get_symptom_history(user_id: str, days: int = 30) -> str:
    """Retrieve recent symptom history for a user.

    Returns a chronological list of all symptoms reported within the
    specified time period, ordered from most recent to oldest. Each
    entry includes the symptom description, severity, timestamp, and
    any suspected medication connection.

    Use this tool when:
      - A user asks about their recent symptoms
      - Looking for patterns in symptom timing or severity
      - Checking if symptoms correlate with specific medications
      - Preparing information for a doctor visit

    Args:
        user_id: The unique identifier of the user.
        days: Number of days to look back (default: 30).

    Returns:
        JSON string containing an array of symptom records, sorted by
        timestamp (most recent first).
    """
    await _ensure_db()
    try:
        symptoms = await db.get_symptom_history(user_id, days)

        symptom_data = [s.model_dump() for s in symptoms]

        return json.dumps(
            {
                "status": "success",
                "period_days": days,
                "symptom_count": len(symptom_data),
                "symptoms": symptom_data,
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool get_symptom_history failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to get symptom history: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def generate_doctor_summary(
    user_id: str,
    patient_name: str = "Patient",
    days: int = 30,
) -> str:
    """Generate a comprehensive summary report suitable for sharing with a doctor.

    This is the most comprehensive reporting tool. It produces a formatted
    text report that includes:
      - All current medications with dosages and schedules
      - Adherence statistics per medication (% taken, missed, late)
      - Recent symptom reports with severity ratings
      - A formatted, printable summary suitable for a medical appointment

    Use this tool when:
      - A user is preparing for a doctor's appointment
      - A user wants a comprehensive overview of their medication status
      - A caregiver needs to share patient information with a provider

    The generated report includes a medical disclaimer noting that all
    data is self-reported.

    ⚕️ MEDICAL DISCLAIMER: This report is generated from self-reported
    data and is intended to supplement — not replace — official medical
    records. Healthcare providers should verify all information.

    Args:
        user_id: The unique identifier of the user/patient.
        patient_name: The patient's name to display on the report
                      (default: 'Patient').
        days: Number of days to include in the report (default: 30).

    Returns:
        A formatted text report that can be printed or shared with a
        healthcare provider. Includes medications, adherence stats,
        symptoms, and medical disclaimer.
    """
    await _ensure_db()
    try:
        summary = await db.generate_doctor_summary(user_id, patient_name, days)

        # Return the formatted summary text directly (not JSON-wrapped)
        # because this output is meant to be read by humans, not parsed.
        # We include the structured data as well for programmatic access.
        return json.dumps(
            {
                "status": "success",
                "formatted_report": summary.summary_text,
                "structured_data": {
                    "generated_at": summary.generated_at,
                    "patient_name": summary.patient_name,
                    "medications": summary.medications,
                    "adherence_reports": [r.model_dump() for r in summary.adherence_reports],
                    "symptoms": summary.symptoms,
                },
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool generate_doctor_summary failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to generate doctor summary: {str(e)}"},
            indent=2,
        )


@mcp.tool()
async def get_todays_schedule(user_id: str) -> str:
    """Get today's medication schedule with dose completion status.

    Shows all medications scheduled for today with:
      - Medication name and dosage
      - Scheduled times
      - How many doses have been logged today
      - Whether all doses for the day are complete

    This is the primary "daily view" tool — use it when:
      - A user asks what medications they need to take today
      - Checking if all medications have been taken
      - Starting a daily medication check-in conversation

    Args:
        user_id: The unique identifier of the user.

    Returns:
        JSON string containing today's schedule with completion status
        for each medication. Includes medication_id for easy dose logging.

    Example response structure:
        {
          "schedule": [
            {
              "medication_name": "Lisinopril",
              "dosage": "10mg",
              "scheduled_times": ["08:00"],
              "doses_logged_today": 1,
              "all_taken": true
            }
          ]
        }
    """
    await _ensure_db()
    try:
        schedule = await db.get_todays_schedule(user_id)

        # Count pending vs completed medications for a quick summary
        total_meds = len(schedule)
        completed = sum(1 for s in schedule if s.get("all_taken", False))
        pending = total_meds - completed

        return json.dumps(
            {
                "status": "success",
                "summary": (
                    f"{completed}/{total_meds} medications completed today. "
                    + (f"{pending} still pending." if pending > 0 else "All done! 🎉")
                ),
                "schedule": schedule,
            },
            indent=2,
        )
    except Exception as e:
        logger.error("Tool get_todays_schedule failed: %s", str(e))
        return json.dumps(
            {"status": "error", "message": f"Failed to get today's schedule: {str(e)}"},
            indent=2,
        )

@mcp.tool()
async def lookup_drug_info(drug_name: str) -> str:
    """Look up official FDA drug label information for a medication.

    Queries the openFDA drug labeling API to retrieve official prescribing
    information including standard dosage ranges, administration guidelines,
    warnings, and contraindications.

    Use this tool BEFORE adding a medication to validate the dosage the user
    provided against the FDA-approved label. This helps catch unusual doses
    that might indicate a typo or misunderstanding.

    Args:
        drug_name: The medication name to look up (e.g., 'metformin',
                   'aspirin', 'lisinopril'). Brand or generic names work.

    Returns:
        JSON string with FDA drug label data including:
        - dosage_and_administration: Standard dosing information
        - dosage_forms_and_strengths: Available dosage forms
        - warnings: Important safety warnings
        - indications_and_usage: What the drug is used for
        - brand_name / generic_name: Official names

    Example usage by the LLM:
        >>> lookup_drug_info("metformin")
        # Returns FDA label info showing typical dose is 500-2550mg/day
        # Agent can then compare with user's requested dose
    """
    import urllib.request
    import urllib.parse
    import urllib.error

    logger.info("Tool lookup_drug_info: Looking up '%s' on openFDA", drug_name)

    try:
        # Query openFDA drug label API — free, no API key required
        # Search both brand_name and generic_name for best coverage
        query = urllib.parse.quote(drug_name)
        url = (
            f"https://api.fda.gov/drug/label.json"
            f"?search=(openfda.brand_name:{query}+openfda.generic_name:{query})"
            f"&limit=1"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "MedMinder/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if not data.get("results"):
            logger.info("Tool lookup_drug_info: No FDA data found for '%s'", drug_name)
            return json.dumps({
                "status": "not_found",
                "drug_name": drug_name,
                "message": (
                    f"No FDA drug label found for '{drug_name}'. "
                    "This may be a non-US drug or an uncommon name. "
                    "Use your medical knowledge to validate the dose."
                ),
            }, indent=2)

        result = data["results"][0]

        # Extract key fields, truncating very long text for LLM readability
        def _extract(field_name: str, max_len: int = 1500) -> str | None:
            val = result.get(field_name)
            if isinstance(val, list) and val:
                text = val[0]
                return text[:max_len] + "..." if len(text) > max_len else text
            return None

        drug_info = {
            "status": "found",
            "drug_name": drug_name,
            "brand_name": result.get("openfda", {}).get("brand_name", [None])[0] if result.get("openfda") else None,
            "generic_name": result.get("openfda", {}).get("generic_name", [None])[0] if result.get("openfda") else None,
            "dosage_and_administration": _extract("dosage_and_administration"),
            "dosage_forms_and_strengths": _extract("dosage_forms_and_strengths", 500),
            "indications_and_usage": _extract("indications_and_usage", 500),
            "warnings": _extract("warnings", 800),
            "source": "openFDA Drug Label API (api.fda.gov)",
            "disclaimer": (
                "This information is from the official FDA drug label. "
                "Always defer to the patient's prescribing physician for "
                "actual dosage decisions."
            ),
        }

        logger.info(
            "Tool lookup_drug_info: Found FDA data for '%s' (brand: %s)",
            drug_name, drug_info.get("brand_name"),
        )
        return json.dumps(drug_info, indent=2)

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return json.dumps({
                "status": "not_found",
                "drug_name": drug_name,
                "message": f"No FDA drug label found for '{drug_name}'.",
            }, indent=2)
        logger.error("Tool lookup_drug_info HTTP error: %s", str(e))
        return json.dumps({
            "status": "error",
            "message": f"FDA API error: {str(e)}. Use your medical knowledge.",
        }, indent=2)
    except Exception as e:
        logger.error("Tool lookup_drug_info failed: %s", str(e))
        return json.dumps({
            "status": "error",
            "message": f"Could not reach FDA API: {str(e)}. Use your medical knowledge.",
        }, indent=2)


# ===========================================================================
#  Server Entry Point
# ===========================================================================

if __name__ == "__main__":
    # When run directly, start the MCP server using stdio transport.
    #
    # stdio transport is the default and most compatible option:
    #   - Works with Claude Desktop, Cursor, and other MCP clients
    #   - Uses stdin/stdout for JSON-RPC communication
    #   - No network configuration needed
    #
    # For SSE (Server-Sent Events) transport, use: mcp.run(transport="sse")
    logger.info("Starting MedMinder MCP Server...")
    logger.info("Database path: %s", DB_PATH)
    logger.info("Transport: stdio")
    logger.info("Tools registered: 11")
    mcp.run()
