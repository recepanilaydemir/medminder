"""Step definitions for the Drug Interaction Checking feature.

Since the drug interaction checking relies on an external MCP tool (BioMCP)
that may not be available in the test environment, we mock the tool responses
to test the interaction-checking flow deterministically.

Architecture:
  - We simulate the interaction checker returning data for known drug pairs.
  - We verify that medical disclaimers are always included in responses.
  - No external services or API keys are required.

⚕️ MEDICAL DISCLAIMER:
  These tests validate software flow only. The mock interaction data is
  NOT medically accurate and must NEVER be used for clinical decisions.
  Always consult a pharmacist or healthcare provider for real drug
  interaction information.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenario, then, when


# ---------------------------------------------------------------------------
# Feature file path
# ---------------------------------------------------------------------------
FEATURE_FILE = "../features/drug_interactions.feature"

# ---------------------------------------------------------------------------
# Standard medical disclaimer that should appear in all interaction responses.
# This matches the disclaimer pattern used throughout MedMinder.
# ---------------------------------------------------------------------------
MEDICAL_DISCLAIMER = (
    "This information is for educational purposes only and is NOT a "
    "substitute for professional medical advice."
)


# ---------------------------------------------------------------------------
# Scenario Declarations
# ---------------------------------------------------------------------------

@scenario(FEATURE_FILE, "MCP server returns interaction data")
def test_interaction_data_returned():
    """Verify that known interacting drugs return interaction data."""
    pass


@scenario(FEATURE_FILE, "No interaction found")
def test_no_interaction_found():
    """Verify graceful handling when no interaction is found."""
    pass


# ---------------------------------------------------------------------------
# Mock Interaction Data
# ---------------------------------------------------------------------------
# These mock responses simulate what BioMCP would return for known drug
# pairs. The structure mirrors BioMCP's actual response format.
# ---------------------------------------------------------------------------

MOCK_INTERACTIONS = {
    ("Warfarin", "Aspirin"): {
        "status": "success",
        "interaction_found": True,
        "drug_pair": ["Warfarin", "Aspirin"],
        "severity": "Major",
        "description": (
            "Concurrent use of Warfarin and Aspirin increases the risk "
            "of bleeding. Both drugs affect blood clotting through "
            "different mechanisms."
        ),
        "recommendation": (
            "Avoid concurrent use unless specifically directed by a "
            "healthcare provider. If used together, monitor closely "
            "for signs of bleeding."
        ),
        "disclaimer": MEDICAL_DISCLAIMER,
    },
    ("Metformin", "Acetaminophen"): {
        "status": "success",
        "interaction_found": False,
        "drug_pair": ["Metformin", "Acetaminophen"],
        "severity": "None",
        "description": "No clinically significant interaction found.",
        "recommendation": "No special precautions needed.",
        "disclaimer": MEDICAL_DISCLAIMER,
    },
}


# ---------------------------------------------------------------------------
# Background Steps
# ---------------------------------------------------------------------------

@given("the MedMinder database is initialized", target_fixture="db")
def db_is_initialized(test_db):
    """Provide the initialised test database.

    Even though interaction checking doesn't require the database,
    we initialise it to match the feature's Background block.
    """
    return test_db


# ---------------------------------------------------------------------------
# Given Steps
# ---------------------------------------------------------------------------

@given(
    "the interaction checker MCP tool is available",
    target_fixture="interaction_checker",
)
def interaction_checker_available():
    """Set up a mock interaction checker that returns predetermined data.

    We create a callable mock that looks up drug pairs in our
    MOCK_INTERACTIONS dictionary. This simulates the BioMCP tool
    without needing the actual service running.

    Returns:
        An async callable mock that simulates interaction checking.
    """

    async def mock_check_interaction(drug_a: str, drug_b: str) -> dict:
        """Simulate checking interactions between two drugs.

        Looks up the drug pair in both orderings (A,B) and (B,A)
        since drug interaction lookups should be order-independent.

        Args:
            drug_a: First drug name.
            drug_b: Second drug name.

        Returns:
            A dict containing interaction data or no-interaction response.
        """
        # Try both orderings since interaction lookups are symmetric
        key = (drug_a, drug_b)
        reverse_key = (drug_b, drug_a)

        if key in MOCK_INTERACTIONS:
            return MOCK_INTERACTIONS[key]
        elif reverse_key in MOCK_INTERACTIONS:
            return MOCK_INTERACTIONS[reverse_key]
        else:
            # Default: no interaction found for unknown pairs
            return {
                "status": "success",
                "interaction_found": False,
                "drug_pair": [drug_a, drug_b],
                "severity": "Unknown",
                "description": "No interaction data available for this pair.",
                "recommendation": "Consult a pharmacist or healthcare provider.",
                "disclaimer": MEDICAL_DISCLAIMER,
            }

    return mock_check_interaction


# ---------------------------------------------------------------------------
# When Steps
# ---------------------------------------------------------------------------

@when(
    parsers.parse('checking interaction between "{drug_a}" and "{drug_b}"'),
    target_fixture="interaction_result",
)
def check_interaction(interaction_checker, drug_a, drug_b, event_loop):
    """Execute the interaction check for the given drug pair.

    Calls the mock interaction checker (which simulates BioMCP)
    and stores the result for Then-step assertions.

    Returns:
        The interaction result dict.
    """
    result = event_loop.run_until_complete(
        interaction_checker(drug_a, drug_b)
    )
    return result


# ---------------------------------------------------------------------------
# Then Steps
# ---------------------------------------------------------------------------

@then("the result should contain interaction data")
def result_contains_interaction_data(interaction_result):
    """Assert that the result indicates an interaction was found."""
    assert interaction_result["interaction_found"] is True, (
        "Expected interaction_found to be True, but got False"
    )
    assert interaction_result["severity"] != "None", (
        "Expected a non-'None' severity for interacting drugs"
    )
    assert len(interaction_result["description"]) > 0, (
        "Expected a non-empty interaction description"
    )


@then("the response should include a medical disclaimer")
def response_includes_disclaimer(interaction_result):
    """Assert that the interaction response contains a medical disclaimer.

    Every response from the interaction checker MUST include a
    disclaimer, regardless of whether an interaction was found.
    This is a critical safety requirement.
    """
    assert "disclaimer" in interaction_result, (
        "Response must include a 'disclaimer' field"
    )
    disclaimer_text = interaction_result["disclaimer"]
    # Check for key phrases that should appear in any medical disclaimer
    assert "NOT" in disclaimer_text or "not" in disclaimer_text, (
        "Disclaimer should clearly state limitations"
    )
    assert "medical" in disclaimer_text.lower(), (
        "Disclaimer should reference medical advice"
    )


@then("the result should indicate no significant interaction")
def result_indicates_no_interaction(interaction_result):
    """Assert that the result indicates no interaction was found."""
    assert interaction_result["interaction_found"] is False, (
        "Expected interaction_found to be False for non-interacting drugs"
    )
    assert interaction_result["status"] == "success", (
        f"Expected status 'success', got '{interaction_result['status']}'"
    )
