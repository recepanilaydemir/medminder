Feature: Drug Interaction Checking
  As a patient taking multiple medications
  I want to check for drug interactions
  So that I can avoid dangerous combinations

  Background:
    Given the MedMinder database is initialized

  Scenario: MCP server returns interaction data
    Given the interaction checker MCP tool is available
    When checking interaction between "Warfarin" and "Aspirin"
    Then the result should contain interaction data
    And the response should include a medical disclaimer

  Scenario: No interaction found
    Given the interaction checker MCP tool is available
    When checking interaction between "Metformin" and "Acetaminophen"
    Then the result should indicate no significant interaction
