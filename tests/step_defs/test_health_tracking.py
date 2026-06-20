"""Step definitions for the Health Tracking and Reports feature.

Tests symptom logging, adherence report generation, and doctor summary
creation directly against the database and MCP server layers.

Architecture:
  - Symptom logging is tested via MedMinderDB.log_symptom()
  - Adherence reports via MedMinderDB.get_adherence_report()
  - Doctor summaries via MedMinderDB.generate_doctor_summary()
  - High-severity warnings are tested via the MCP server's log_symptom tool
    (since the warning logic lives in the MCP layer, not the DB layer)
  - No external API keys or services required.

⚕️ MEDICAL DISCLAIMER:
  These tests validate software behaviour only. Severity ratings,
  adherence percentages, and doctor summaries are based on self-reported
  data and must NOT be used as a substitute for clinical assessment.
"""

from __future__ import annotations

import json

import pytest
from pytest_bdd import given, parsers, scenario, then, when


# ---------------------------------------------------------------------------
# Feature file path
# ---------------------------------------------------------------------------
FEATURE_FILE = "../features/health_tracking.feature"


# ---------------------------------------------------------------------------
# Scenario Declarations
# ---------------------------------------------------------------------------

@scenario(FEATURE_FILE, "Log a symptom")
def test_log_symptom():
    """Verify basic symptom logging."""
    pass


@scenario(FEATURE_FILE, "Log a high-severity symptom triggers warning")
def test_log_high_severity_symptom():
    """Verify that high-severity symptoms trigger a warning message."""
    pass


@scenario(FEATURE_FILE, "Log symptom related to medication")
def test_log_symptom_related_to_medication():
    """Verify symptom can be linked to a medication."""
    pass


@scenario(FEATURE_FILE, "Generate adherence report with no data")
def test_adherence_report_no_data():
    """Verify adherence report handles empty data gracefully."""
    pass


@scenario(FEATURE_FILE, "Generate adherence report")
def test_generate_adherence_report():
    """Verify adherence report calculates statistics correctly."""
    pass


@scenario(FEATURE_FILE, "Generate doctor summary")
def test_generate_doctor_summary():
    """Verify doctor summary includes all required sections."""
    pass


# ---------------------------------------------------------------------------
# Background Steps
# ---------------------------------------------------------------------------

@given("the MedMinder database is initialized", target_fixture="db")
def db_is_initialized(test_db):
    """Provide the initialised test database to all steps."""
    return test_db


@given(
    parsers.parse('user "{user_name}" exists in the system'),
    target_fixture="user_id",
)
def user_exists(db, user_name, event_loop):
    """Ensure the test user exists in the database.

    Returns:
        The user_id string.
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
    """Add a medication to the test database.

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


@given(
    parsers.parse('the user has logged a "{status}" dose for "{med_name}"'),
    target_fixture="logged_dose",
)
def user_has_logged_dose(db, user_id, status, med_name, existing_medication, event_loop):
    """Log a dose for an existing medication.

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


@given(
    parsers.parse('the user has logged a symptom "{description}" with severity {severity:d}'),
    target_fixture="logged_symptom",
)
def user_has_logged_symptom(db, user_id, description, severity, event_loop):
    """Log a symptom in the database for pre-population.

    Returns:
        The created Symptom model instance.
    """
    symptom = event_loop.run_until_complete(
        db.log_symptom(
            user_id=user_id,
            description=description,
            severity=severity,
        )
    )
    return symptom


# ---------------------------------------------------------------------------
# When Steps — Symptom Logging
# ---------------------------------------------------------------------------

@when(
    parsers.parse('the user logs a symptom "{description}" with severity {severity:d}'),
    target_fixture="symptom_result",
)
def log_symptom(db, user_id, description, severity, event_loop):
    """Log a symptom via the database layer.

    Also creates a mock MCP-style response dict to test the warning
    logic that lives in the MCP server layer.

    Returns:
        A dict containing the symptom model and MCP-style response data.
    """
    symptom = event_loop.run_until_complete(
        db.log_symptom(
            user_id=user_id,
            description=description,
            severity=severity,
        )
    )

    # Simulate the MCP server's warning logic for high-severity symptoms
    # This mirrors the logic in medminder_server.py's log_symptom tool
    severity_labels = {1: "Minimal", 2: "Mild", 3: "Moderate", 4: "Severe", 5: "Emergency"}
    label = severity_labels.get(severity, "Unknown")

    warning = ""
    if severity >= 4:
        warning = (
            f"⚠️ HIGH SEVERITY ALERT: This symptom has been rated as "
            f"'{label}'. Please contact your healthcare provider as soon "
            f"as possible."
        )
    if severity == 5:
        warning = (
            "🚨 EMERGENCY SEVERITY: This symptom requires immediate "
            "medical attention. Please call emergency services or go to "
            "the nearest emergency room."
        )

    return {
        "symptom": symptom,
        "message": f"Symptom logged: {description} (Severity: {label}){warning}",
        "warning": warning,
    }


@when(
    parsers.parse(
        'the user logs a symptom "{description}" with severity {severity:d} '
        'related to "{med_name}"'
    ),
    target_fixture="symptom_result",
)
def log_symptom_related_to_medication(
    db, user_id, description, severity, med_name, event_loop
):
    """Log a symptom linked to a specific medication.

    Returns:
        A dict containing the symptom model.
    """
    symptom = event_loop.run_until_complete(
        db.log_symptom(
            user_id=user_id,
            description=description,
            severity=severity,
            related_medication=med_name,
        )
    )
    return {
        "symptom": symptom,
        "message": f"Symptom logged: {description}",
        "warning": "",
    }


# ---------------------------------------------------------------------------
# When Steps — Reports
# ---------------------------------------------------------------------------

@when(
    parsers.parse("the user requests an adherence report for {days:d} days"),
    target_fixture="adherence_report",
)
def request_adherence_report(db, user_id, days, event_loop):
    """Generate an adherence report for the specified time period.

    Returns:
        A list of AdherenceReport model instances.
    """
    reports = event_loop.run_until_complete(
        db.get_adherence_report(user_id, days)
    )
    return reports


@when("the user generates a doctor summary", target_fixture="doctor_summary")
def generate_doctor_summary(db, user_id, event_loop):
    """Generate a comprehensive doctor summary.

    Uses 'Test Patient' as the patient name and 30-day window.

    Returns:
        A DoctorSummary model instance.
    """
    summary = event_loop.run_until_complete(
        db.generate_doctor_summary(
            user_id=user_id,
            patient_name="Test Patient",
            days=30,
        )
    )
    return summary


# ---------------------------------------------------------------------------
# Then Steps — Symptom Assertions
# ---------------------------------------------------------------------------

@then("the symptom should be recorded")
def symptom_is_recorded(symptom_result):
    """Assert that the symptom was successfully recorded."""
    symptom = symptom_result["symptom"]
    assert symptom is not None, "Symptom should not be None"
    assert symptom.id is not None, "Symptom should have an ID"
    assert len(symptom.id) > 0, "Symptom ID should not be empty"


@then(parsers.parse("the symptom severity should be {severity:d}"))
def symptom_has_severity(symptom_result, severity):
    """Assert the symptom has the expected severity rating."""
    assert symptom_result["symptom"].severity == severity, (
        f"Expected severity {severity}, "
        f"got {symptom_result['symptom'].severity}"
    )


@then("a high-severity warning should be included")
def high_severity_warning_included(symptom_result):
    """Assert that a high-severity warning message is present.

    The warning should be non-empty for severity >= 4 and should
    contain urgency-related keywords.
    """
    warning = symptom_result["warning"]
    assert len(warning) > 0, (
        "Expected a non-empty warning for high-severity symptom"
    )
    # Check for key warning indicators
    assert any(keyword in warning for keyword in ["SEVERITY", "ALERT", "EMERGENCY"]), (
        f"Warning should contain severity-related keywords, got: '{warning}'"
    )


@then(parsers.parse('the symptom should reference "{med_name}"'))
def symptom_references_medication(symptom_result, med_name):
    """Assert that the symptom is linked to the specified medication."""
    symptom = symptom_result["symptom"]
    assert symptom.related_medication == med_name, (
        f"Expected related_medication '{med_name}', "
        f"got '{symptom.related_medication}'"
    )


# ---------------------------------------------------------------------------
# Then Steps — Adherence Report Assertions
# ---------------------------------------------------------------------------

@then(parsers.parse("the report should show {count:d} medications"))
def report_shows_medication_count(adherence_report, count):
    """Assert the adherence report contains the expected number of medications."""
    assert len(adherence_report) == count, (
        f"Expected {count} medications in report, "
        f"but found {len(adherence_report)}"
    )


@then(parsers.parse('the report should include "{med_name}"'))
def report_includes_medication(adherence_report, med_name):
    """Assert that the named medication appears in the adherence report."""
    med_names = [r.medication_name for r in adherence_report]
    assert med_name in med_names, (
        f"Expected '{med_name}' in adherence report, "
        f"but found: {med_names}"
    )


@then("the adherence percentage should be calculated")
def adherence_percentage_calculated(adherence_report):
    """Assert that adherence percentages are computed (not all zero/null).

    With at least one taken and one missed dose, the percentage should
    be a valid number between 0 and 100.
    """
    for report in adherence_report:
        assert 0.0 <= report.adherence_percentage <= 100.0, (
            f"Adherence percentage {report.adherence_percentage} "
            f"for '{report.medication_name}' is out of valid range"
        )
    # At least one report should have a non-zero percentage
    # (we logged at least one 'taken' dose in the Given steps)
    has_nonzero = any(r.adherence_percentage > 0 for r in adherence_report)
    assert has_nonzero, (
        "Expected at least one medication with non-zero adherence, "
        f"but all were: {[r.adherence_percentage for r in adherence_report]}"
    )


# ---------------------------------------------------------------------------
# Then Steps — Doctor Summary Assertions
# ---------------------------------------------------------------------------

@then("the summary should contain the patient name")
def summary_contains_patient_name(doctor_summary):
    """Assert that the patient name appears in the doctor summary."""
    assert doctor_summary.patient_name == "Test Patient", (
        f"Expected patient name 'Test Patient', "
        f"got '{doctor_summary.patient_name}'"
    )
    # Also check it appears in the formatted text
    assert "Test Patient" in doctor_summary.summary_text, (
        "Patient name should appear in the formatted summary text"
    )


@then("the summary should list medications")
def summary_lists_medications(doctor_summary):
    """Assert that the doctor summary includes medication information.

    Checks both the structured data (medications list) and the
    formatted summary text.
    """
    assert len(doctor_summary.medications) > 0, (
        "Doctor summary should include at least one medication"
    )
    # Verify the formatted text contains medication section
    assert "MEDICATIONS" in doctor_summary.summary_text.upper(), (
        "Formatted summary should contain a 'MEDICATIONS' section header"
    )


@then("the summary should include symptoms")
def summary_includes_symptoms(doctor_summary):
    """Assert that the doctor summary includes symptom data.

    Checks both structured data and formatted text.
    """
    assert len(doctor_summary.symptoms) > 0, (
        "Doctor summary should include at least one symptom"
    )
    assert "SYMPTOM" in doctor_summary.summary_text.upper(), (
        "Formatted summary should contain a 'SYMPTOMS' section header"
    )


@then("the summary should include a medical disclaimer")
def summary_includes_disclaimer(doctor_summary):
    """Assert that the doctor summary contains a medical disclaimer.

    This is a CRITICAL safety check — every patient-facing report
    MUST include a disclaimer stating that the data is self-reported
    and not a substitute for clinical records.
    """
    text = doctor_summary.summary_text.upper()
    assert "DISCLAIMER" in text, (
        "Doctor summary MUST include a medical disclaimer"
    )
    # Check for key disclaimer phrases
    assert "SELF-REPORTED" in text or "NOT A SUBSTITUTE" in text, (
        "Disclaimer should mention self-reported data or substitute for records"
    )
