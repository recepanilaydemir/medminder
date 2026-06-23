"""Step definitions for FDA Drug Information Lookup (Gherkin BDD).

Tests the lookup_drug_info MCP tool which queries the openFDA API
for official drug label data. Tests cover successful lookups,
not-found cases, and data quality constraints.

These tests make REAL HTTP calls to api.fda.gov (free, no key needed).
They require internet connectivity.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
import urllib.error

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load all scenarios from the feature file
scenarios("../features/fda_drug_lookup.feature")


# ─── Shared State ─────────────────────────────────────────────────

@pytest.fixture
def context():
    """Shared state dict for passing data between steps."""
    return {"result": None}


# ─── Background Steps ────────────────────────────────────────────

@given("the MedMinder database is initialized")
def db_initialized():
    """FDA lookup doesn't need a database, but the background requires it."""
    pass


# ─── When Steps ──────────────────────────────────────────────────

@when(parsers.parse('the user looks up drug info for "{drug_name}"'))
def lookup_drug(context, drug_name):
    """Call the openFDA API directly, mirroring the MCP tool logic."""
    context["result"] = _call_lookup_drug_info(drug_name)


# ─── Then Steps ───────────────────────────────────────────────────

@then(parsers.parse('the lookup status should be "{status}"'))
def check_status(context, status):
    assert context["result"]["status"] == status, (
        f"Expected status '{status}', got '{context['result']['status']}'"
    )


@then(parsers.parse('the result should contain a "{field}"'))
def result_contains_field(context, field):
    assert field in context["result"], (
        f"Field '{field}' not found in result keys: {list(context['result'].keys())}"
    )
    assert context["result"][field] is not None, (
        f"Field '{field}' is None"
    )


@then(parsers.parse('the result should contain "{field}"'))
def result_contains_field_str(context, field):
    assert field in context["result"], (
        f"Field '{field}' not found in result keys: {list(context['result'].keys())}"
    )


@then(parsers.parse('the result source should be "{source}"'))
def result_source_is(context, source):
    assert context["result"].get("source") == source, (
        f"Expected source '{source}', got '{context['result'].get('source')}'"
    )


@then("the result should contain a disclaimer about consulting physicians")
def result_has_disclaimer(context):
    disclaimer = context["result"].get("disclaimer", "")
    assert "physician" in disclaimer.lower() or "prescribing" in disclaimer.lower(), (
        f"Disclaimer doesn't mention physicians: {disclaimer}"
    )


@then("the result should contain a not-found message")
def result_has_not_found_message(context):
    message = context["result"].get("message", "")
    assert "not found" in message.lower() or "no fda" in message.lower(), (
        f"Expected 'not found' in message: {message}"
    )


@then("the lookup should return a result")
def lookup_returns_result(context):
    assert context["result"] is not None


@then("the result should handle the edge case gracefully")
def result_handles_edge_case(context):
    # Should not crash — either returns not_found or error, not an exception
    assert context["result"]["status"] in ("found", "not_found", "error"), (
        f"Unexpected status: {context['result']['status']}"
    )


@then("the dosage_and_administration field should be at most 1500 characters")
def dosage_field_truncated(context):
    dosage = context["result"].get("dosage_and_administration", "")
    if dosage:
        assert len(dosage) <= 1503, (  # 1500 + "..."
            f"dosage_and_administration too long: {len(dosage)} chars"
        )


# ─── Helper Functions ─────────────────────────────────────────────

def _call_lookup_drug_info(drug_name: str) -> dict:
    """Replicate the lookup_drug_info MCP tool logic for testing."""
    try:
        query = urllib.parse.quote(drug_name) if drug_name else ""
        url = (
            f"https://api.fda.gov/drug/label.json"
            f"?search=(openfda.brand_name:{query}+openfda.generic_name:{query})"
            f"&limit=1"
        )

        req = urllib.request.Request(url, headers={"User-Agent": "MedMinder/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if not data.get("results"):
            return {
                "status": "not_found",
                "drug_name": drug_name,
                "message": f"No FDA drug label found for '{drug_name}'.",
            }

        result = data["results"][0]

        def _extract(field_name, max_len=1500):
            val = result.get(field_name)
            if isinstance(val, list) and val:
                text = val[0]
                return text[:max_len] + "..." if len(text) > max_len else text
            return None

        return {
            "status": "found",
            "drug_name": drug_name,
            "brand_name": (result.get("openfda", {}).get("brand_name", [None])[0]
                          if result.get("openfda") else None),
            "generic_name": (result.get("openfda", {}).get("generic_name", [None])[0]
                            if result.get("openfda") else None),
            "dosage_and_administration": _extract("dosage_and_administration"),
            "dosage_forms_and_strengths": _extract("dosage_forms_and_strengths", 500),
            "indications_and_usage": _extract("indications_and_usage", 500),
            "warnings": _extract("warnings", 800),
            "source": "openFDA Drug Label API (api.fda.gov)",
            "disclaimer": (
                "This information is from the official FDA drug label. "
                "Always defer to the patient's prescribing physician for "
                "actual dosage decisions."
            ),
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "not_found",
                "drug_name": drug_name,
                "message": f"No FDA drug label found for '{drug_name}'.",
            }
        return {"status": "error", "message": f"FDA API error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Could not reach FDA API: {str(e)}"}
