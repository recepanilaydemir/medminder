Feature: FDA Drug Information Lookup
  As a patient or healthcare-aware user
  I want the system to look up official FDA drug labels
  So that I can verify medication details against authoritative data

  Background:
    Given the MedMinder database is initialized

  # ─── Successful Lookups ─────────────────────────────────────────

  Scenario: Look up a common medication by generic name
    When the user looks up drug info for "metformin"
    Then the lookup status should be "found"
    And the result should contain a "generic_name"
    And the result should contain "dosage_and_administration"
    And the result source should be "openFDA Drug Label API (api.fda.gov)"

  Scenario: Look up a medication by brand name
    When the user looks up drug info for "Tylenol"
    Then the lookup status should be "found"
    And the result should contain a "brand_name"

  Scenario: Look up returns dosage forms and strengths
    When the user looks up drug info for "lisinopril"
    Then the lookup status should be "found"
    And the result should contain "dosage_forms_and_strengths"

  Scenario: Look up returns warnings information
    When the user looks up drug info for "aspirin"
    Then the lookup status should be "found"
    And the result should contain "warnings"

  Scenario: Look up includes medical disclaimer
    When the user looks up drug info for "metformin"
    Then the lookup status should be "found"
    And the result should contain a disclaimer about consulting physicians

  # ─── Not Found / Error Cases ────────────────────────────────────

  Scenario: Look up an unknown drug name
    When the user looks up drug info for "XyzNotARealDrug999"
    Then the lookup status should be "not_found"
    And the result should contain a not-found message

  Scenario: Look up handles whitespace-only drug name
    When the user looks up drug info for " "
    Then the lookup should return a result
    And the result should handle the edge case gracefully

  # ─── Data Quality ───────────────────────────────────────────────

  Scenario: Long FDA labels are truncated for readability
    When the user looks up drug info for "metformin"
    Then the lookup status should be "found"
    And the dosage_and_administration field should be at most 1500 characters
