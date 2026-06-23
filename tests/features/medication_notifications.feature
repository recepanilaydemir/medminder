Feature: Medication Reminder Notifications
  As a patient
  I want to receive timely reminders for my medications
  So that I never miss a scheduled dose

  Background:
    Given the MedMinder database is initialized
    And user "test_user" exists in the system

  # ─── Time-Based Reminder Triggering ───────────────────────────

  Scenario: Reminder triggers at the scheduled time
    Given the user has medication "Aspirin" with dosage "81mg" frequency "daily" at times "08:00"
    When the current time is "08:00"
    Then a reminder should be triggered for "Aspirin"

  Scenario: Reminder triggers within 5-minute window
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00"
    When the current time is "08:03"
    Then a reminder should be triggered for "Metformin"

  Scenario: No reminder before scheduled time
    Given the user has medication "Lisinopril" with dosage "10mg" frequency "daily" at times "14:00"
    When the current time is "13:55"
    Then no reminder should be triggered for "Lisinopril"

  Scenario: No reminder long after scheduled time
    Given the user has medication "Lisinopril" with dosage "10mg" frequency "daily" at times "08:00"
    When the current time is "08:10"
    Then no reminder should be triggered for "Lisinopril"

  # ─── Deduplication ────────────────────────────────────────────

  Scenario: Reminder is not repeated after first notification
    Given the user has medication "Aspirin" with dosage "81mg" frequency "daily" at times "09:00"
    And a reminder was already shown for "Aspirin" at "09:00"
    When the current time is "09:02"
    Then no reminder should be triggered for "Aspirin"

  # ─── Completed Doses ──────────────────────────────────────────

  Scenario: No reminder for already-taken medication
    Given the user has medication "Aspirin" with dosage "81mg" frequency "daily" at times "08:00"
    And all doses for "Aspirin" are already taken today
    When the current time is "08:00"
    Then no reminder should be triggered for "Aspirin"

  # ─── Quick Dose Logging ──────────────────────────────────────

  Scenario: Log a taken dose via quick action
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user logs a quick dose for "Metformin" as "taken"
    Then the dose should be recorded as "taken"

  Scenario: Skip a dose via quick action
    Given the user has medication "Metformin" with dosage "500mg" frequency "twice daily" at times "08:00,20:00"
    When the user logs a quick dose for "Metformin" as "missed"
    Then the dose should be recorded as "missed"
