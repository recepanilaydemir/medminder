"""Step definitions for Medication Reminder Notifications (Gherkin BDD).

Tests the notification engine logic:
  1. Time-window matching (at time, within window, before, after)
  2. Deduplication (no repeat notifications)
  3. Completed dose suppression
  4. Quick dose logging via the database layer

This tests the LOGIC of the notification engine, not the DOM/UI.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load all scenarios from the feature file
scenarios("../features/medication_notifications.feature")


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


# ─── Time Window Logic (mirrors notifications.js) ────────────────

def is_within_window(current: str, target: str, window_minutes: int = 5) -> bool:
    """Python port of _isWithinWindow from notifications.js."""
    c_h, c_m = map(int, current.split(":"))
    t_h, t_m = map(int, target.split(":"))
    current_total = c_h * 60 + c_m
    target_total = t_h * 60 + t_m
    diff = current_total - target_total
    return 0 <= diff <= window_minutes


# ─── Shared State ─────────────────────────────────────────────────

@pytest.fixture
def context():
    return {
        "db": None,
        "user_id": "test_user_001",
        "medications": {},       # name -> medication record
        "notified_doses": set(), # "medId:HH:MM"
        "triggered": [],         # list of medication names that triggered
        "dose_log": None,
    }


# ─── Background Steps ────────────────────────────────────────────

@given("the MedMinder database is initialized", target_fixture="test_db")
def db_initialized(tmp_path):
    from backend.db.database import MedMinderDB
    db = MedMinderDB(db_path=str(tmp_path / "test_notifications.db"))
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
    med = run_async(test_db.add_medication(
        user_id=context["user_id"],
        name=name,
        dosage=dosage,
        frequency=frequency,
        times=times_list,
    ))
    context["medications"][name] = {
        "medication_id": med.id,
        "medication_name": med.name,
        "dosage": med.dosage,
        "scheduled_times": times_list,
        "all_taken": False,
    }


@given(parsers.parse('a reminder was already shown for "{name}" at "{time}"'))
def reminder_already_shown(context, name, time):
    med = context["medications"][name]
    key = f"{med['medication_id']}:{time}"
    context["notified_doses"].add(key)


@given(parsers.parse('all doses for "{name}" are already taken today'))
def all_doses_taken(test_db, context, name):
    med = context["medications"][name]
    # Log enough doses to cover all scheduled times
    for _ in med["scheduled_times"]:
        run_async(test_db.log_dose(med["medication_id"], "taken"))
    med["all_taken"] = True


# ─── When Steps ──────────────────────────────────────────────────

@when(parsers.parse('the current time is "{current_time}"'))
def check_at_time(context, current_time):
    """Simulate the notification engine's schedule check at a given time."""
    context["triggered"] = []

    for name, med in context["medications"].items():
        if med["all_taken"]:
            continue

        for scheduled_time in med["scheduled_times"]:
            key = f"{med['medication_id']}:{scheduled_time}"
            if key in context["notified_doses"]:
                continue

            if is_within_window(current_time, scheduled_time, 5):
                context["notified_doses"].add(key)
                context["triggered"].append(name)


@when(parsers.parse('the user logs a quick dose for "{name}" as "{status}"'))
def log_quick_dose(test_db, context, name, status):
    med = context["medications"][name]
    # Map "skipped" to "missed" as the API does
    db_status = "missed" if status == "skipped" else status
    dose_log = run_async(test_db.log_dose(med["medication_id"], db_status))
    context["dose_log"] = dose_log


# ─── Then Steps ───────────────────────────────────────────────────

@then(parsers.parse('a reminder should be triggered for "{name}"'))
def reminder_triggered(context, name):
    assert name in context["triggered"], (
        f"Expected reminder for '{name}' but triggered: {context['triggered']}"
    )


@then(parsers.parse('no reminder should be triggered for "{name}"'))
def no_reminder_triggered(context, name):
    assert name not in context["triggered"], (
        f"Expected NO reminder for '{name}' but it was triggered"
    )


@then(parsers.parse('the dose should be recorded as "{status}"'))
def dose_recorded(context, status):
    assert context["dose_log"] is not None, "No dose log was recorded"
    assert context["dose_log"].status == status, (
        f"Expected status '{status}', got '{context['dose_log'].status}'"
    )
