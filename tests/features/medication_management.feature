Feature: Medication Management
  As a patient
  I want to manage my medication list
  So that I can track what I'm taking

  Background:
    Given the MedMinder database is initialized
    And user "test_user" exists in the system

  Scenario: Add a new medication
    When the user adds medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    Then the medication "Metformin" should be in the active list
    And the medication should have dosage "500mg"

  Scenario: Add medication with notes
    When the user adds medication "Lisinopril" with dosage "10mg" frequency "once daily" at times "08:00" with notes "Take on empty stomach"
    Then the medication "Lisinopril" should be in the active list
    And the medication notes should contain "empty stomach"

  Scenario: List medications when empty
    When the user lists their medications
    Then the medication list should be empty

  Scenario: Remove a medication
    Given the user has medication "Aspirin" with dosage "81mg" frequency "once daily" at times "09:00"
    When the user removes medication "Aspirin"
    Then the medication "Aspirin" should not be in the active list

  Scenario: Log a taken dose
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user logs a "taken" dose for "Metformin"
    Then the dose should be recorded as "taken"

  Scenario: Log a missed dose with reason
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user logs a missed dose for "Metformin" with reason "forgot"
    Then the dose should be recorded as "missed"
    And the dose notes should contain "forgot"
