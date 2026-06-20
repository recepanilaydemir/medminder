Feature: Medication Reminders and Scheduling
  As a patient
  I want to see my daily medication schedule
  So that I know when to take each medication

  Background:
    Given the MedMinder database is initialized
    And user "test_user" exists in the system

  Scenario: View empty schedule
    When the user requests today's schedule
    Then the schedule should be empty

  Scenario: View schedule with medications
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    And the user has medication "Lisinopril" with dosage "10mg" frequency "once daily" at times "08:00"
    When the user requests today's schedule
    Then the schedule should contain 2 medications
    And the schedule should include "Metformin"
    And the schedule should include "Lisinopril"

  Scenario: Schedule shows completion status
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    And the user has logged a "taken" dose for "Metformin"
    When the user requests today's schedule
    Then the schedule should show doses logged for "Metformin"
