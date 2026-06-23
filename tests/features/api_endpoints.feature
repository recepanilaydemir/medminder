Feature: REST API Endpoints
  As a frontend application
  I want reliable API endpoints
  So that I can display medication data and interact with the AI agent

  Background:
    Given the MedMinder API server is running
    And the test database is initialized

  # ─── Chat Endpoint ──────────────────────────────────────────────

  Scenario: Send a chat message successfully
    Given a valid API key is configured
    When the client sends a POST to "/api/chat" with message "Hello"
    Then the response status code should be 200
    And the response should contain a "response" field
    And the response should contain a "trace" field

  Scenario: Chat response includes agent trace data
    Given a valid API key is configured
    When the client sends a POST to "/api/chat" with message "What medications am I on?"
    Then the response should contain a "trace" field
    And the trace should be a list of event objects
    And each trace event should have a "type" field
    And each trace event should have an "author" field

  Scenario: Chat trace includes MCP server attribution
    Given a valid API key is configured
    When the client sends a POST to "/api/chat" with message "Add Aspirin 81mg once daily at 08:00"
    Then the response should contain a "trace" field
    And tool call trace events should include "mcp_server" field

  Scenario: Chat without API key returns error
    When the client sends a POST to "/api/chat" with message "Hello" without API key
    Then the response status code should be 500
    And the response should contain an error message

  # ─── Configuration Endpoint ─────────────────────────────────────

  Scenario: Set API key via configuration
    When the client sends a POST to "/api/config" with api_key "test-key-123"
    Then the response status code should be 200
    And the response should confirm the API key was set

  Scenario: Get current configuration
    When the client sends a GET to "/api/config"
    Then the response status code should be 200
    And the response should indicate whether an API key is configured

  # ─── Medications Endpoint ───────────────────────────────────────

  Scenario: List medications when none exist
    When the client sends a GET to "/api/medications"
    Then the response status code should be 200
    And the response body should contain a "medications" array
    And the medications array should be empty

  Scenario: List medications returns active medications
    Given medication "Metformin" with dosage "500mg" exists in the database
    When the client sends a GET to "/api/medications"
    Then the response status code should be 200
    And the medications array should contain "Metformin"

  # ─── Schedule Endpoint ──────────────────────────────────────────

  Scenario: Get today's schedule when empty
    When the client sends a GET to "/api/schedule/today"
    Then the response status code should be 200
    And the response body should contain a "schedule" array

  Scenario: Get today's schedule with medications
    Given medication "Metformin" with dosage "500mg" at times "08:00,20:00" exists in the database
    When the client sends a GET to "/api/schedule/today"
    Then the response status code should be 200
    And the schedule should include "Metformin"

  # ─── Static File Serving ────────────────────────────────────────

  Scenario: Serve the frontend index page
    When the client sends a GET to "/"
    Then the response status code should be 200
    And the response content type should contain "text/html"

  Scenario: Serve CSS files
    When the client sends a GET to "/css/style.css"
    Then the response status code should be 200

  Scenario: Serve JavaScript files
    When the client sends a GET to "/js/app.js"
    Then the response status code should be 200

  # ─── Error Handling ─────────────────────────────────────────────

  Scenario: Unknown API route returns 404
    When the client sends a GET to "/api/nonexistent"
    Then the response status code should be 404

  Scenario: Session persistence across chat messages
    Given a valid API key is configured
    When the client sends a POST to "/api/chat" with message "Hello"
    And the client sends another POST to "/api/chat" with message "What did I just say?"
    Then both responses should use the same session
