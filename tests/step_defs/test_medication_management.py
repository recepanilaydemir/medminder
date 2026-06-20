"""Step definitions for the Medication Management feature.

Tests the core medication CRUD operations and dose logging directly
against the database layer — no Gemini API key required.

Architecture:
  These tests hit the MedMinderDB class directly rather than going through
  the agent or even the MCP server. This is intentional because:
    1. Database logic is the foundation — if it's broken, everything is broken.
    2. DB tests are fast, deterministic, and need zero external services.
    3. MCP server tests would be integration tests (tested separately).

Each scenario gets a fresh isolated database via the `test_db` fixture
from conftest.py.

⚕️ MEDICAL DISCLAIMER:
  These tests validate software behaviour only. They do NOT verify
  medical correctness or clinical safety.
"""

from __future__ import annotations

import json

import pytest
from pytest_bdd import given, parsers, scenario, then, when


# ---------------------------------------------------------------------------
# Feature file path (relative to this file)
# ---------------------------------------------------------------------------
FEATURE_FILE = "../features/medication_management.feature"


# ---------------------------------------------------------------------------
# Scenario Declarations
# ---------------------------------------------------------------------------
# pytest-bdd requires explicit @scenario decorators so it can discover
# which scenarios map to which test functions during collection.
# ---------------------------------------------------------------------------

@scenario(FEATURE_FILE, "Add a new medication")
def test_add_new_medication():
    """Verify that a new medication can be added to the system."""
    pass


@scenario(FEATURE_FILE, "Add medication with notes")
def test_add_medication_with_notes():
    """Verify that a medication can be added with optional notes."""
    pass


@scenario(FEATURE_FILE, "List medications when empty")
def test_list_medications_empty():
    """Verify empty list is returned when user has no medications."""
    pass


@scenario(FEATURE_FILE, "Remove a medication")
def test_remove_medication():
    """Verify that a medication can be soft-deleted."""
    pass


@scenario(FEATURE_FILE, "Log a taken dose")
def test_log_taken_dose():
    """Verify that a taken dose is recorded correctly."""
    pass


@scenario(FEATURE_FILE, "Log a missed dose with reason")
def test_log_missed_dose_with_reason():
    """Verify that a missed dose with reason is recorded correctly."""
    pass


# ---------------------------------------------------------------------------
# Background Steps
# ---------------------------------------------------------------------------
# These run before every scenario in the feature file, setting up the
# shared preconditions (database + user).
# ---------------------------------------------------------------------------

@given("the MedMinder database is initialized", target_fixture="db")
def db_is_initialized(test_db):
    """Provide the initialised test database to all steps.

    The `test_db` fixture (from conftest.py) already calls `init_db()`,
    so we just pass it through as the 'db' fixture for step definitions.
    """
    return test_db


@given(
    parsers.parse('user "{user_name}" exists in the system'),
    target_fixture="user_id",
)
def user_exists(db, user_name, event_loop):
    """Ensure the test user exists in the database.

    We use `get_or_create_user` which is idempotent — safe to call
    multiple times with the same user_id.

    Args:
        db: The test database instance.
        user_name: Name for the test user.
        event_loop: asyncio event loop for running async code.

    Returns:
        The user_id string, stored as the 'user_id' fixture.
    """
    user = event_loop.run_until_complete(
        db.get_or_create_user(user_name, user_name)
    )
    return user.id


# ---------------------------------------------------------------------------
# Given Steps — Pre-populate Data
# ---------------------------------------------------------------------------

@given(
    parsers.parse(
        'the user has medication "{med_name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}"'
    ),
    target_fixture="existing_medication",
)
def user_has_medication(db, user_id, med_name, dosage, frequency, times, event_loop):
    """Pre-populate a medication for scenarios that need existing data.

    Parses the comma-separated times string into a list and adds
    the medication to the database.

    Returns:
        The created Medication model instance.
    """
    times_list = [t.strip() for t in times.split(",")]
    medication = event_loop.run_until_complete(
        db.add_medication(
            user_id=user_id,
            name=med_name,
            dosage=dosage,
            frequency=frequency,
            times=times_list,
        )
    )
    return medication


# ---------------------------------------------------------------------------
# When Steps — Actions
# ---------------------------------------------------------------------------

@when(
    parsers.parse(
        'the user adds medication "{med_name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}"'
    ),
    target_fixture="added_medication",
)
def add_medication(db, user_id, med_name, dosage, frequency, times, event_loop):
    """Add a medication via the database layer.

    Returns:
        The created Medication model instance.
    """
    times_list = [t.strip() for t in times.split(",")]
    medication = event_loop.run_until_complete(
        db.add_medication(
            user_id=user_id,
            name=med_name,
            dosage=dosage,
            frequency=frequency,
            times=times_list,
        )
    )
    return medication


@when(
    parsers.parse(
        'the user adds medication "{med_name}" with dosage "{dosage}" '
        'frequency "{frequency}" at times "{times}" with notes "{notes}"'
    ),
    target_fixture="added_medication",
)
def add_medication_with_notes(
    db, user_id, med_name, dosage, frequency, times, notes, event_loop
):
    """Add a medication with optional notes via the database layer.

    Returns:
        The created Medication model instance.
    """
    times_list = [t.strip() for t in times.split(",")]
    medication = event_loop.run_until_complete(
        db.add_medication(
            user_id=user_id,
            name=med_name,
            dosage=dosage,
            frequency=frequency,
            times=times_list,
            notes=notes,
        )
    )
    return medication


@when("the user lists their medications", target_fixture="medication_list")
def list_medications(db, user_id, event_loop):
    """List all active medications for the user.

    Returns:
        A list of Medication model instances.
    """
    meds = event_loop.run_until_complete(db.list_medications(user_id))
    return meds


@when(
    parsers.parse('the user removes medication "{med_name}"'),
    target_fixture="removal_result",
)
def remove_medication(db, user_id, med_name, existing_medication, event_loop):
    """Remove (soft-delete) a medication by its name.

    First looks up the medication by name to get its ID, then
    calls remove_medication. The `existing_medication` fixture
    ensures the medication was created in a prior Given step.

    Returns:
        True if the medication was successfully deactivated.
    """
    # Use the existing_medication fixture's ID for removal
    result = event_loop.run_until_complete(
        db.remove_medication(existing_medication.id)
    )
    return result


@when(
    parsers.parse('the user logs a "{status}" dose for "{med_name}"'),
    target_fixture="dose_log",
)
def log_dose(db, user_id, status, med_name, existing_medication, event_loop):
    """Log a dose event for an existing medication.

    Returns:
        The created DoseLog model instance.
    """
    dose = event_loop.run_until_complete(
        db.log_dose(
            medication_id=existing_medication.id,
            status=status,
        )
    )
    return dose


@when(
    parsers.parse(
        'the user logs a missed dose for "{med_name}" with reason "{reason}"'
    ),
    target_fixture="dose_log",
)
def log_missed_dose_with_reason(db, user_id, med_name, reason, existing_medication, event_loop):
    """Log a missed dose with a reason note.

    The reason is stored in the dose log's notes field, prefixed with
    'Reason: ' to match the MCP server's convention.

    Returns:
        The created DoseLog model instance.
    """
    dose = event_loop.run_until_complete(
        db.log_dose(
            medication_id=existing_medication.id,
            status="missed",
            notes=f"Reason: {reason}",
        )
    )
    return dose


# ---------------------------------------------------------------------------
# Then Steps — Assertions
# ---------------------------------------------------------------------------

@then(
    parsers.parse('the medication "{med_name}" should be in the active list')
)
def medication_in_active_list(db, user_id, med_name, event_loop):
    """Assert that the named medication appears in the user's active list."""
    meds = event_loop.run_until_complete(db.list_medications(user_id))
    med_names = [m.name for m in meds]
    assert med_name in med_names, (
        f"Expected '{med_name}' in active medications, "
        f"but found: {med_names}"
    )


@then(parsers.parse('the medication should have dosage "{dosage}"'))
def medication_has_dosage(db, user_id, dosage, event_loop):
    """Assert that the most recently added medication has the expected dosage."""
    meds = event_loop.run_until_complete(db.list_medications(user_id))
    # Check the last medication added (most recent in alphabetical order may differ,
    # so we check if ANY medication has this dosage)
    dosages = [m.dosage for m in meds]
    assert dosage in dosages, (
        f"Expected dosage '{dosage}' in medications, "
        f"but found dosages: {dosages}"
    )


@then(parsers.parse('the medication notes should contain "{text}"'))
def medication_notes_contain(db, user_id, text, event_loop):
    """Assert that at least one medication's notes contain the expected text."""
    meds = event_loop.run_until_complete(db.list_medications(user_id))
    found = any(m.notes and text in m.notes for m in meds)
    assert found, (
        f"Expected at least one medication with notes containing '{text}', "
        f"but notes were: {[m.notes for m in meds]}"
    )


@then("the medication list should be empty")
def medication_list_is_empty(medication_list):
    """Assert that the medication list returned by the When step is empty."""
    assert len(medication_list) == 0, (
        f"Expected empty medication list, but found {len(medication_list)} items"
    )


@then(
    parsers.parse('the medication "{med_name}" should not be in the active list')
)
def medication_not_in_active_list(db, user_id, med_name, event_loop):
    """Assert the medication is no longer in the active list after removal."""
    meds = event_loop.run_until_complete(db.list_medications(user_id))
    med_names = [m.name for m in meds]
    assert med_name not in med_names, (
        f"Expected '{med_name}' to be removed from active list, "
        f"but it was still found in: {med_names}"
    )


@then(parsers.parse('the dose should be recorded as "{status}"'))
def dose_recorded_as(dose_log, status):
    """Assert that the dose log has the expected status."""
    assert dose_log.status == status, (
        f"Expected dose status '{status}', but got '{dose_log.status}'"
    )


@then(parsers.parse('the dose notes should contain "{text}"'))
def dose_notes_contain(dose_log, text):
    """Assert that the dose log notes contain the expected text."""
    assert dose_log.notes is not None, "Dose log notes should not be None"
    assert text in dose_log.notes, (
        f"Expected dose notes to contain '{text}', "
        f"but got: '{dose_log.notes}'"
    )
