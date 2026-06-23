Feature: Medication Safety Checks
  As a patient adding medications
  I want the system to check for duplicates and validate dosages
  So that I am warned about potential errors before they are saved

  Background:
    Given the MedMinder database is initialized
    And user "test_user" exists in the system

  # ─── Duplicate Detection ────────────────────────────────────────

  Scenario: Warn when adding an exact duplicate medication
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "duplicate_exact" warning
    And the medication should not be added to the database yet

  Scenario: Warn when adding same medication at different times
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "Metformin" with dosage "500mg" frequency "once daily" at times "14:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "duplicate_different_time" warning

  Scenario: Warn when adding medication with similar name
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "Metformin ER" with dosage "750mg" frequency "once daily" at times "20:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "similar_name" warning

  Scenario: No duplicate warning for different medications
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "Lisinopril" with dosage "10mg" frequency "once daily" at times "08:00"
    Then the response status should be "requires_confirmation"
    And the warnings should not include a "duplicate_exact" warning
    And the warnings should not include a "similar_name" warning

  # ─── FDA Dose Validation ────────────────────────────────────────

  Scenario: FDA drug label is retrieved for known medication
    When the user adds medication "Aspirin" with dosage "81mg" frequency "once daily" at times "08:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "fda_info" warning
    And the FDA info should contain dosage and administration data

  Scenario: FDA lookup handles unknown medication gracefully
    When the user adds medication "XyzMadeUpDrug123" with dosage "50mg" frequency "once daily" at times "08:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "fda_not_found" warning

  # ─── Confirmation Flow ──────────────────────────────────────────

  Scenario: Medication is added after user confirms warnings
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "Metformin" with dosage "1000mg" frequency "once daily" at times "08:00" with confirmation
    Then the response status should be "success"
    And the medication "Metformin" should appear twice in the active list

  Scenario: Medication is not added without confirmation
    When the user adds medication "Aspirin" with dosage "5000mg" frequency "once daily" at times "08:00"
    Then the response status should be "requires_confirmation"
    And the medication "Aspirin" should not be in the active list

  # ─── Edge Cases ─────────────────────────────────────────────────

  Scenario: Case-insensitive duplicate detection
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user adds medication "metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "duplicate_exact" warning

  Scenario: Adding first medication with no duplicates still validates FDA
    When the user adds medication "Lisinopril" with dosage "10mg" frequency "once daily" at times "08:00"
    Then the response status should be "requires_confirmation"
    And the warnings should include a "fda_info" warning
    And the warnings should not include a "duplicate_exact" warning
