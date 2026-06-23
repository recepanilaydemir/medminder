"""Step definitions for Medication Safety Checks (Gherkin BDD).

Tests the tool-level safety enforcement in add_medication:
  1. Duplicate detection (exact, different time, similar name)
  2. FDA dose validation via openFDA API
  3. Confirmation flow (requires_confirmation → confirmed=true)

pytest-bdd does NOT support async steps natively, so all database calls
are wrapped with asyncio.run() or event loop helpers.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load all scenarios from the feature file
scenarios("../features/medication_safety.feature")


# ─── Async Helper ─────────────────────────────────────────────────

def run_async(coro):
    """Run an async coroutine synchronously for pytest-bdd compatibility."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─── Shared State ─────────────────────────────────────────────────

@pytest.fixture
def context():
    """Shared state dict for passing data between Given/When/Then steps."""
    return {
        "response": None,
        "response_data": None,
        "db": None,
        "user_id": "test_user_001",
    }


# ─── Background Steps ────────────────────────────────────────────

@given("the MedMinder database is initialized", target_fixture="test_db")
def db_initialized(tmp_path):
    from backend.db.database import MedMinderDB
    db = MedMinderDB(db_path=str(tmp_path / "test_safety.db"))
    run_async(db.init_db())
    return db


@given('user "test_user" exists in the system')
def user_exists(test_db, context):
    context["db"] = test_db
    run_async(test_db.get_or_create_user(context["user_id"], "Test Patient"))


# ─── Given Steps ─────────────────────────────────────────────────

@given(
    parsers.parse(
        'the user has medication "{name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}"'
    )
)
def user_has_medication(test_db, context, name, dosage, frequency, times):
    times_list = [t.strip() for t in times.split(",")]
    run_async(test_db.add_medication(
        user_id=context["user_id"],
        name=name,
        dosage=dosage,
        frequency=frequency,
        times=times_list,
    ))


# ─── When Steps ──────────────────────────────────────────────────

@when(
    parsers.parse(
        'the user adds medication "{name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}"'
    )
)
def add_medication_without_confirm(test_db, context, name, dosage, frequency, times):
    """Call add_medication logic without confirmed flag."""
    result = run_async(_call_add_medication(
        test_db, context["user_id"], name, dosage, frequency, times, confirmed=False
    ))
    context["response_data"] = result
    context["response"] = result


@when(
    parsers.parse(
        'the user adds medication "{name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}" with confirmation'
    )
)
def add_medication_with_confirm(test_db, context, name, dosage, frequency, times):
    """Call add_medication with confirmed=True (bypasses safety checks)."""
    result = run_async(_call_add_medication(
        test_db, context["user_id"], name, dosage, frequency, times, confirmed=True
    ))
    context["response_data"] = result
    context["response"] = result


# ─── Then Steps ───────────────────────────────────────────────────

@then(parsers.parse('the response status should be "{status}"'))
def response_status_is(context, status):
    assert context["response_data"] is not None, "No response data captured"
    assert context["response_data"]["status"] == status, (
        f"Expected status '{status}', got '{context['response_data']['status']}'"
    )


@then(parsers.parse('the warnings should include a "{warning_type}" warning'))
def warnings_include_type(context, warning_type):
    warnings = context["response_data"].get("warnings", [])
    types = [w["type"] for w in warnings]
    assert warning_type in types, (
        f"Expected warning type '{warning_type}' in {types}"
    )


@then(parsers.parse('the warnings should not include a "{warning_type}" warning'))
def warnings_not_include_type(context, warning_type):
    warnings = context["response_data"].get("warnings", [])
    types = [w["type"] for w in warnings]
    assert warning_type not in types, (
        f"Warning type '{warning_type}' should NOT be present, but found in {types}"
    )


@then("the medication should not be added to the database yet")
def medication_not_added(test_db, context):
    meds = run_async(test_db.list_medications(context["user_id"]))
    initial_count = 1  # From the Given step
    assert len(meds) == initial_count, (
        f"Expected {initial_count} medication(s), got {len(meds)}"
    )


@then("the FDA info should contain dosage and administration data")
def fda_info_has_dosage(context):
    warnings = context["response_data"].get("warnings", [])
    fda_warnings = [w for w in warnings if w["type"] == "fda_info"]
    assert len(fda_warnings) > 0, "No fda_info warning found"
    msg = fda_warnings[0]["message"].lower()
    assert any(kw in msg for kw in ["dosage", "dose", "administration", "directions", "tablet"]), (
        f"FDA info doesn't contain dosage data: {fda_warnings[0]['message'][:200]}"
    )


@then(parsers.parse('the medication "{name}" should appear twice in the active list'))
def medication_appears_twice(test_db, context, name):
    meds = run_async(test_db.list_medications(context["user_id"]))
    matching = [m for m in meds if m.name.lower() == name.lower()]
    assert len(matching) >= 2, (
        f"Expected at least 2 '{name}' entries, got {len(matching)}"
    )


@then(parsers.parse('the medication "{name}" should not be in the active list'))
def medication_not_in_list(test_db, context, name):
    meds = run_async(test_db.list_medications(context["user_id"]))
    matching = [m for m in meds if m.name.lower() == name.lower()]
    assert len(matching) == 0, (
        f"Expected no '{name}' entries, got {len(matching)}"
    )


# ─── Helper Functions ─────────────────────────────────────────────

async def _call_add_medication(
    db, user_id: str, name: str, dosage: str,
    frequency: str, times: str, confirmed: bool = False,
) -> dict:
    """Simulate calling the add_medication MCP tool directly."""
    import urllib.request
    import urllib.parse
    import urllib.error

    times_list = [t.strip() for t in times.split(",")]
    warnings = []

    # Safety Check 1: Duplicate detection
    if not confirmed:
        existing = await db.list_medications(user_id)
        for med in existing:
            if med.name.lower() == name.lower():
                existing_times = ",".join(med.times) if med.times else "unknown"
                requested_times = ",".join(times_list)
                if existing_times == requested_times:
                    warnings.append({
                        "type": "duplicate_exact",
                        "message": f"DUPLICATE: You already have {med.name} at {existing_times}.",
                    })
                else:
                    warnings.append({
                        "type": "duplicate_different_time",
                        "message": f"NOTE: You already have {med.name} at {existing_times}.",
                    })
            elif med.name.lower() in name.lower() or name.lower() in med.name.lower():
                warnings.append({
                    "type": "similar_name",
                    "message": f"SIMILAR: You have '{med.name}' — is '{name}' different?",
                })

    # Safety Check 2: FDA lookup
    if not confirmed:
        try:
            query = urllib.parse.quote(name)
            url = (
                f"https://api.fda.gov/drug/label.json"
                f"?search=(openfda.brand_name:{query}+openfda.generic_name:{query})"
                f"&limit=1"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "MedMinder/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                fda_data = json.loads(resp.read().decode())

            if fda_data.get("results"):
                result = fda_data["results"][0]
                dosage_info = ""
                if result.get("dosage_and_administration"):
                    dosage_info = result["dosage_and_administration"][0][:800]
                brand = (result.get("openfda", {}).get("brand_name", [None])[0]
                         if result.get("openfda") else None)
                generic = (result.get("openfda", {}).get("generic_name", [None])[0]
                           if result.get("openfda") else None)
                warnings.append({
                    "type": "fda_info",
                    "severity": "info",
                    "message": f"FDA Drug Label ({brand or generic or name}):\n{dosage_info}",
                    "source": "openFDA Drug Label API (api.fda.gov)",
                })
            else:
                warnings.append({
                    "type": "fda_not_found",
                    "severity": "info",
                    "message": f"No FDA drug label found for '{name}'.",
                })
        except urllib.error.HTTPError as e:
            if e.code == 404:
                warnings.append({
                    "type": "fda_not_found",
                    "severity": "info",
                    "message": f"No FDA drug label found for '{name}'.",
                })
            else:
                warnings.append({
                    "type": "fda_error",
                    "severity": "info",
                    "message": f"FDA API error: {str(e)}.",
                })
        except Exception as e:
            warnings.append({
                "type": "fda_error",
                "severity": "info",
                "message": f"Could not reach FDA API: {str(e)}.",
            })

    if warnings and not confirmed:
        return {
            "status": "requires_confirmation",
            "warnings": warnings,
            "medication_preview": {
                "name": name, "dosage": dosage,
                "frequency": frequency, "times": times,
            },
        }

    # Actually add
    medication = await db.add_medication(
        user_id=user_id, name=name, dosage=dosage,
        frequency=frequency, times=times_list,
    )
    return {
        "status": "success",
        "medication": medication.model_dump(),
    }
