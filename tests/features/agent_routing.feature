Feature: Multi-Agent Orchestration
  As a user interacting with MedMinder
  I want my requests routed to the correct specialist agent
  So that I get accurate and relevant responses

  Background:
    Given the MedMinder multi-agent system is initialized
    And a valid API key is configured

  # ─── Routing to ScheduleAgent ───────────────────────────────────

  Scenario: Schedule-related message routes to ScheduleAgent
    When the user sends "What do I take today?"
    Then the trace should show routing to "ScheduleAgent"

  Scenario: Adding medication routes to ScheduleAgent
    When the user sends "Add Metformin 500mg twice daily at 08:00 and 20:00"
    Then the trace should show routing to "ScheduleAgent"
    And the trace should include a tool call to "add_medication"

  Scenario: Removing medication routes to ScheduleAgent
    When the user sends "Remove my aspirin"
    Then the trace should show routing to "ScheduleAgent"

  Scenario: Dose logging routes to ScheduleAgent
    When the user sends "I just took my morning pills"
    Then the trace should show routing to "ScheduleAgent"

  # ─── Routing to InteractionAgent ────────────────────────────────

  Scenario: Drug interaction query routes to InteractionAgent
    When the user sends "Can I take ibuprofen with aspirin?"
    Then the trace should show routing to "InteractionAgent"

  Scenario: Side effects query routes to InteractionAgent
    When the user sends "What are the side effects of Lisinopril?"
    Then the trace should show routing to "InteractionAgent"

  # ─── Routing to HealthAgent ─────────────────────────────────────

  Scenario: Symptom report routes to HealthAgent
    When the user sends "I have a headache and feel dizzy"
    Then the trace should show routing to "HealthAgent"

  Scenario: Adherence report routes to HealthAgent
    When the user sends "How well have I been taking my meds?"
    Then the trace should show routing to "HealthAgent"

  Scenario: Doctor summary routes to HealthAgent
    When the user sends "Generate a report for my doctor appointment"
    Then the trace should show routing to "HealthAgent"

  # ─── Direct Handling (Orchestrator) ─────────────────────────────

  Scenario: Greeting is handled by the orchestrator directly
    When the user sends "Hello!"
    Then the response should not route to a sub-agent
    And the response should be a friendly greeting

  Scenario: Asking about capabilities is handled directly
    When the user sends "What can you help me with?"
    Then the response should describe MedMinder's capabilities

  # ─── Medical Disclaimer ────────────────────────────────────────

  Scenario: Agent responses include medical disclaimer when relevant
    When the user sends "Should I increase my Metformin dose?"
    Then the response should include a medical disclaimer
    And the response should recommend consulting a healthcare provider

  # ─── Emergency Protocol ─────────────────────────────────────────

  Scenario: Emergency symptoms trigger urgent response
    When the user sends "I think I took too many pills and feel very dizzy"
    Then the response should include emergency contact information
    And the response should mention calling emergency services or poison control
