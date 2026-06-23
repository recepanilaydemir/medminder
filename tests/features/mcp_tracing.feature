Feature: MCP Tool Tracing and Transparency
  As a user of MedMinder
  I want to see which tools and MCP servers the agent used
  So that I can understand how the agent reached its conclusions

  Background:
    Given the MedMinder database is initialized
    And a valid API key is configured

  # ─── Trace Event Structure ──────────────────────────────────────

  Scenario: Trace captures tool call events
    When the user sends a message that triggers a tool call
    Then the trace should contain at least one "tool_call" event
    And the tool_call event should include "tool_name"
    And the tool_call event should include "tool_args"

  Scenario: Trace captures tool response events
    When the user sends a message that triggers a tool call
    Then the trace should contain at least one "tool_response" event
    And the tool_response event should include "tool_name"
    And the tool_response event should include "result_preview"

  Scenario: Trace captures text response events
    When the user sends "Hello"
    Then the trace should contain at least one "text" event
    And the text event should include "author"

  # ─── MCP Server Attribution ─────────────────────────────────────

  Scenario: MedMinder MCP tools are attributed correctly
    When the agent calls tool "list_medications"
    Then the MCP server should be "MedMinder MCP Server"

  Scenario: FDA lookup tool is attributed correctly
    When the agent calls tool "lookup_drug_info"
    Then the MCP server should be "MedMinder MCP → openFDA API"

  Scenario: Agent routing tool is attributed correctly
    When the agent calls tool "transfer_to_agent"
    Then the MCP server should be "ADK Agent Router"

  Scenario: BioMCP tools are attributed correctly
    When the agent calls tool "search_drug_interactions"
    Then the MCP server should be "BioMCP (DDInter/PubMed)"

  Scenario: drug-interaction-mcp tools are attributed correctly
    When the agent calls tool "check_interaction"
    Then the MCP server should be "drug-interaction-mcp"

  Scenario: Unknown tools get a fallback attribution
    When the agent calls tool "some_unknown_tool"
    Then the MCP server should be "External MCP"

  # ─── Trace Summary ─────────────────────────────────────────────

  Scenario: Trace summary counts agents and tools correctly
    When the user sends "Add Aspirin 81mg once daily at 08:00"
    Then the trace should count at least 1 agent
    And the trace should count at least 1 tool
    And the trace should report the total number of steps
