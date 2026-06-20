Feature: Health Tracking and Reports
  As a patient
  I want to track symptoms and generate health reports
  So that I can share accurate information with my doctor

  Background:
    Given the MedMinder database is initialized
    And user "test_user" exists in the system

  Scenario: Log a symptom
    When the user logs a symptom "headache" with severity 3
    Then the symptom should be recorded
    And the symptom severity should be 3

  Scenario: Log a high-severity symptom triggers warning
    When the user logs a symptom "chest pain" with severity 5
    Then the symptom should be recorded
    And a high-severity warning should be included

  Scenario: Log symptom related to medication
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user logs a symptom "nausea" with severity 2 related to "Metformin"
    Then the symptom should be recorded
    And the symptom should reference "Metformin"

  Scenario: Generate adherence report with no data
    When the user requests an adherence report for 30 days
    Then the report should show 0 medications

  Scenario: Generate adherence report
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    And the user has logged a "taken" dose for "Metformin"
    And the user has logged a "missed" dose for "Metformin"
    When the user requests an adherence report for 30 days
    Then the report should include "Metformin"
    And the adherence percentage should be calculated

  Scenario: Generate doctor summary
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    And the user has logged a symptom "headache" with severity 2
    When the user generates a doctor summary
    Then the summary should contain the patient name
    And the summary should list medications
    And the summary should include symptoms
    And the summary should include a medical disclaimer
