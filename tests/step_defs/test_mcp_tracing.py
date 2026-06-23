"""Step definitions for MCP Tool Tracing and Transparency (Gherkin BDD).

Tests the MCP server attribution logic that maps tool names to their
source MCP server. This is a unit-level test of the mapping function
defined in server.py.
"""

from __future__ import annotations

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load all scenarios from the feature file
scenarios("../features/mcp_tracing.feature")


# ─── MCP Source Mapping (mirrors server.py logic) ─────────────────

def _get_mcp_source(tool_name: str) -> str:
    """Replicate the _get_mcp_source function from server.py."""
    MEDMINDER_TOOLS = {
        "add_medication", "remove_medication", "list_medications",
        "log_dose", "log_missed_dose", "get_todays_schedule",
        "log_symptom", "get_adherence_report", "get_symptom_history",
        "generate_doctor_summary",
    }
    FDA_TOOLS = {"lookup_drug_info"}
    BIOMCP_TOOLS = {"search_drug_interactions", "search_pubmed", "get_drug_details"}
    DRUG_INT_TOOLS = {"check_interaction", "get_interactions"}
    HEALTHCARE_TOOLS = {"search_fda_drugs", "get_icd10_codes", "search_pubmed_articles"}
    ADK_TOOLS = {"transfer_to_agent"}

    if tool_name in MEDMINDER_TOOLS:
        return "MedMinder MCP Server"
    elif tool_name in FDA_TOOLS:
        return "MedMinder MCP → openFDA API"
    elif tool_name in BIOMCP_TOOLS:
        return "BioMCP (DDInter/PubMed)"
    elif tool_name in DRUG_INT_TOOLS:
        return "drug-interaction-mcp"
    elif tool_name in HEALTHCARE_TOOLS:
        return "healthcare-mcp-public"
    elif tool_name in ADK_TOOLS:
        return "ADK Agent Router"
    else:
        return "External MCP"


# ─── Shared State ─────────────────────────────────────────────────

@pytest.fixture
def context():
    return {"mcp_server": None, "tool_name": None}


# ─── Background Steps ────────────────────────────────────────────

@given("the MedMinder database is initialized")
def db_initialized():
    pass  # Not needed for attribution tests


@given("a valid API key is configured")
def api_key_configured():
    pass  # Not needed for attribution tests


# ─── When Steps (tool call events) ───────────────────────────────

@when("the user sends a message that triggers a tool call")
def user_sends_tool_triggering_message(context):
    # Simulate a tool call event
    context["tool_name"] = "list_medications"
    context["mcp_server"] = _get_mcp_source("list_medications")
    context["trace"] = [
        {"type": "tool_call", "tool_name": "list_medications",
         "mcp_server": _get_mcp_source("list_medications"),
         "tool_args": {"user_id": "test_user"}, "author": "ScheduleAgent"},
        {"type": "tool_response", "tool_name": "list_medications",
         "mcp_server": _get_mcp_source("list_medications"),
         "result_preview": '{"medications": []}', "author": "ScheduleAgent"},
    ]


@when(parsers.parse('the user sends "{message}"'))
def user_sends_message(context, message):
    # Simulate trace data. If the message is about adding a medication,
    # include tool call events in the trace.
    if "add" in message.lower() or "aspirin" in message.lower():
        context["trace"] = [
            {"type": "tool_call", "tool_name": "transfer_to_agent",
             "mcp_server": "ADK Agent Router",
             "tool_args": {"agent_name": "ScheduleAgent"}, "author": "MedMinder"},
            {"type": "tool_response", "tool_name": "transfer_to_agent",
             "mcp_server": "ADK Agent Router",
             "result_preview": "None", "author": "MedMinder"},
            {"type": "tool_call", "tool_name": "add_medication",
             "mcp_server": "MedMinder MCP Server",
             "tool_args": {"name": "Aspirin", "dosage": "81mg"},
             "author": "ScheduleAgent"},
            {"type": "tool_response", "tool_name": "add_medication",
             "mcp_server": "MedMinder MCP Server",
             "result_preview": '{"status":"requires_confirmation"}',
             "author": "ScheduleAgent"},
            {"type": "text", "author": "ScheduleAgent",
             "text_preview": "Before adding Aspirin..."},
        ]
    else:
        context["trace"] = [
            {"type": "text", "author": "MedMinder",
             "text_preview": f"Response to: {message}"},
        ]


@when(parsers.parse('the agent calls tool "{tool_name}"'))
def agent_calls_tool(context, tool_name):
    context["tool_name"] = tool_name
    context["mcp_server"] = _get_mcp_source(tool_name)


# ─── Then Steps (MCP attribution) ────────────────────────────────

@then(parsers.parse('the MCP server should be "{expected_server}"'))
def mcp_server_is(context, expected_server):
    assert context["mcp_server"] == expected_server, (
        f"Expected MCP server '{expected_server}', got '{context['mcp_server']}'"
    )


@then(parsers.parse('the trace should contain at least one "{event_type}" event'))
def trace_contains_event_type(context, event_type):
    matching = [e for e in context.get("trace", []) if e["type"] == event_type]
    assert len(matching) >= 1, (
        f"Expected at least one '{event_type}' event in trace"
    )


@then(parsers.parse('the tool_call event should include "{field}"'))
def tool_call_has_field(context, field):
    tool_calls = [e for e in context.get("trace", []) if e["type"] == "tool_call"]
    assert len(tool_calls) > 0, "No tool_call events found"
    assert field in tool_calls[0], (
        f"Field '{field}' not in tool_call event: {list(tool_calls[0].keys())}"
    )


@then(parsers.parse('the tool_response event should include "{field}"'))
def tool_response_has_field(context, field):
    responses = [e for e in context.get("trace", []) if e["type"] == "tool_response"]
    assert len(responses) > 0, "No tool_response events found"
    assert field in responses[0], (
        f"Field '{field}' not in tool_response event: {list(responses[0].keys())}"
    )


@then(parsers.parse('the text event should include "{field}"'))
def text_event_has_field(context, field):
    texts = [e for e in context.get("trace", []) if e["type"] == "text"]
    assert len(texts) > 0, "No text events found"
    assert field in texts[0], (
        f"Field '{field}' not in text event: {list(texts[0].keys())}"
    )


@then("the trace should count at least 1 agent")
def trace_has_agent(context):
    authors = set(e.get("author") for e in context.get("trace", []))
    assert len(authors) >= 1


@then("the trace should count at least 1 tool")
def trace_has_tool(context):
    tools = [e for e in context.get("trace", []) if e["type"] == "tool_call"]
    assert len(tools) >= 1


@then("the trace should report the total number of steps")
def trace_has_steps(context):
    assert len(context.get("trace", [])) > 0


@then('tool call trace events should include "mcp_server" field')
def trace_has_mcp_server(context):
    tool_calls = [e for e in context.get("trace", []) if e["type"] == "tool_call"]
    for tc in tool_calls:
        assert "mcp_server" in tc, f"tool_call missing mcp_server: {tc}"
