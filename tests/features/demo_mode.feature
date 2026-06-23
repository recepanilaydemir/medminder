Feature: Interactive Demo Mode
  As a new visitor or Kaggle judge
  I want to try an interactive demo without an API key
  So that I can understand MedMinder's capabilities quickly

  # ─── Demo Availability ────────────────────────────────────────

  Scenario: Demo button is visible on setup screen
    Given the user is on the setup screen
    Then a "Try Interactive Demo" button should be visible

  Scenario: Demo can be started without an API key
    Given the user is on the setup screen
    When the user clicks "Try Interactive Demo"
    Then the main app should be displayed
    And a "DEMO MODE" banner should appear at the top

  # ─── Demo Script Content ──────────────────────────────────────

  Scenario: Demo walks through medication addition
    Given demo mode is active
    Then the demo should show a simulated "Add Lisinopril" conversation
    And the agent response should include FDA verification data

  Scenario: Demo shows drug interaction checking
    Given demo mode is active
    Then the demo should show a drug interaction check
    And the response should mention interaction severity

  Scenario: Demo shows symptom logging
    Given demo mode is active
    Then the demo should show symptom logging for dizziness
    And the response should mention side effect information

  Scenario: Demo shows dashboard with populated data
    Given demo mode is active
    When the demo navigates to the dashboard
    Then adherence stats should be displayed
    And the schedule timeline should show medication entries

  Scenario: Demo shows medication reminder notification
    Given demo mode is active
    Then a reminder banner should appear for a medication

  # ─── Demo Controls ────────────────────────────────────────────

  Scenario: Demo can be exited at any time
    Given demo mode is active
    When the user clicks "Exit Demo"
    Then the setup screen should be displayed
    And the demo overlay should be removed

  Scenario: Chat input is disabled during demo
    Given demo mode is active
    Then the chat input should be disabled
    And the send button should be disabled
