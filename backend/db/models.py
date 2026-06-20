"""
MedMinder Pydantic Models
=========================

This module defines the core data models for the MedMinder medication tracking
system. All models use Pydantic v2 BaseModel for:
  - Automatic validation of incoming data
  - JSON serialization/deserialization
  - Clear schema documentation (used by MCP tool discovery)

Design Decisions:
  - UUIDs are stored as strings for SQLite compatibility (SQLite has no native
    UUID type). We generate them with uuid4() for guaranteed uniqueness.
  - Timestamps are stored as ISO-8601 strings rather than datetime objects so
    they survive JSON round-trips without custom serializers.
  - Severity is constrained to 1-5 via Pydantic's Field validator, mapping to:
    1=minimal, 2=mild, 3=moderate, 4=severe, 5=emergency.
  - DoseLog status uses Literal type for compile-time safety — only 'taken',
    'missed', or 'late' are valid values.

⚕️ MEDICAL DISCLAIMER:
  This software is for INFORMATIONAL and EDUCATIONAL purposes only.
  It is NOT a substitute for professional medical advice, diagnosis, or
  treatment. Always seek the advice of a qualified healthcare provider
  with any questions regarding medications or medical conditions.
  Never disregard professional medical advice or delay seeking it because
  of information provided by this application.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Medication Model
# ---------------------------------------------------------------------------
class Medication(BaseModel):
    """Represents a single medication that a user is tracking.

    The `times` field stores the scheduled dosing times as a list of 24-hour
    formatted strings (e.g., ['08:00', '20:00']). This design allows flexible
    scheduling — once daily, twice daily, or any custom pattern.

    The `active` flag enables soft-deletion: rather than removing medication
    records (which would break referential integrity with DoseLog), we simply
    mark them inactive. This preserves historical adherence data.
    """

    id: str = Field(
        ...,
        description="Unique identifier (UUID4) for this medication record.",
    )
    user_id: str = Field(
        ...,
        description="ID of the user who owns this medication.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of the medication (e.g., 'Lisinopril', 'Metformin').",
    )
    dosage: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Dosage amount and unit (e.g., '10mg', '500mg', '2 tablets').",
    )
    frequency: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="How often the medication is taken (e.g., 'twice daily', 'every 8 hours').",
    )
    times: list[str] = Field(
        ...,
        min_length=1,
        description="Scheduled times in 24-hour format, e.g. ['08:00', '20:00'].",
    )
    start_date: str = Field(
        ...,
        description="Date when the medication regimen started (ISO-8601 date string).",
    )
    active: bool = Field(
        default=True,
        description="Whether the medication is currently active. False = soft-deleted.",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional notes (e.g., 'take with food', 'avoid grapefruit').",
    )

    @field_validator("times", mode="before")
    @classmethod
    def validate_times_format(cls, v: list[str]) -> list[str]:
        """Ensure each time entry looks like HH:MM in 24-hour format.

        We do a lightweight check here — full datetime parsing happens at
        the application layer when building schedules.
        """
        if isinstance(v, str):
            # Handle comma-separated string input (from MCP tool calls)
            v = [t.strip() for t in v.split(",")]
        for time_str in v:
            parts = time_str.strip().split(":")
            if len(parts) != 2:
                raise ValueError(
                    f"Invalid time format '{time_str}'. Expected HH:MM (e.g., '08:00')."
                )
            hour, minute = parts
            if not (hour.isdigit() and minute.isdigit()):
                raise ValueError(
                    f"Invalid time format '{time_str}'. Hour and minute must be numeric."
                )
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError(
                    f"Invalid time '{time_str}'. Hour must be 0-23, minute must be 0-59."
                )
        return v


# ---------------------------------------------------------------------------
# Dose Log Model
# ---------------------------------------------------------------------------
class DoseLog(BaseModel):
    """Records whether a specific dose was taken, missed, or taken late.

    Each DoseLog entry is linked to a Medication via `medication_id`. The
    `status` field uses a Literal type to restrict values — this is critical
    for accurate adherence calculations. A dose can be:
      - 'taken': Patient took the medication on time
      - 'missed': Patient did not take the medication
      - 'late':   Patient took the medication but outside the scheduled window

    Design note: We track 'late' separately from 'taken' because late doses
    can indicate adherence barriers (forgetfulness, side effects causing
    avoidance, etc.) that are clinically relevant.
    """

    id: str = Field(
        ...,
        description="Unique identifier (UUID4) for this dose log entry.",
    )
    medication_id: str = Field(
        ...,
        description="ID of the medication this dose log relates to.",
    )
    timestamp: str = Field(
        ...,
        description="ISO-8601 timestamp when this dose event was recorded.",
    )
    status: Literal["taken", "missed", "late"] = Field(
        ...,
        description="Dose status: 'taken', 'missed', or 'late'.",
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional notes about this dose (e.g., 'took 30 min late').",
    )


# ---------------------------------------------------------------------------
# Symptom Model
# ---------------------------------------------------------------------------
class Symptom(BaseModel):
    """Tracks a symptom reported by the user.

    Symptom tracking serves two purposes:
      1. Correlating symptoms with medications to identify potential side effects
      2. Providing doctors with a timeline of patient-reported symptoms

    The severity scale (1-5) maps to:
      1 = Minimal — barely noticeable
      2 = Mild    — noticeable but doesn't affect daily activities
      3 = Moderate — affects some daily activities
      4 = Severe  — significantly limits daily activities
      5 = Emergency — requires immediate medical attention

    ⚕️ DISCLAIMER: Severity ratings are subjective self-reports and should
    NOT be used as a substitute for clinical assessment.
    """

    id: str = Field(
        ...,
        description="Unique identifier (UUID4) for this symptom entry.",
    )
    user_id: str = Field(
        ...,
        description="ID of the user who reported this symptom.",
    )
    timestamp: str = Field(
        ...,
        description="ISO-8601 timestamp when the symptom was reported.",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of the symptom (e.g., 'headache', 'dizziness').",
    )
    severity: int = Field(
        ...,
        ge=1,
        le=5,
        description="Severity on a 1-5 scale (1=minimal, 5=emergency).",
    )
    related_medication: Optional[str] = Field(
        default=None,
        description="Name of the medication suspected to cause this symptom, if any.",
    )


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------
class User(BaseModel):
    """Represents a MedMinder user.

    We keep the User model intentionally lean — MedMinder is not an auth
    system. The user_id is provided externally (e.g., from an LLM session
    or a simple login). We store just enough to personalize reports.
    """

    id: str = Field(
        ...,
        description="Unique user identifier.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name of the user.",
    )
    created_at: str = Field(
        ...,
        description="ISO-8601 timestamp when the user account was created.",
    )


# ---------------------------------------------------------------------------
# Adherence Report Model
# ---------------------------------------------------------------------------
class AdherenceReport(BaseModel):
    """Aggregated adherence statistics for a single medication.

    This model is computed (not stored) — it's generated on-the-fly from
    DoseLog entries. The adherence_percentage is calculated as:

        adherence_percentage = (taken / total_doses) * 100

    Note: 'late' doses are counted separately and NOT included in the
    adherence percentage. This is a deliberate clinical decision — while
    late doses still provide therapeutic benefit, they indicate a pattern
    that healthcare providers should be aware of.

    ⚕️ DISCLAIMER: Adherence percentages are based on self-reported data
    and may not reflect actual medication intake.
    """

    medication_name: str = Field(
        ...,
        description="Name of the medication this report covers.",
    )
    total_doses: int = Field(
        ...,
        ge=0,
        description="Total number of expected doses in the reporting period.",
    )
    taken: int = Field(
        ...,
        ge=0,
        description="Number of doses confirmed as taken on time.",
    )
    missed: int = Field(
        ...,
        ge=0,
        description="Number of doses confirmed as missed.",
    )
    late: int = Field(
        ...,
        ge=0,
        description="Number of doses taken late.",
    )
    adherence_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of doses taken on time: (taken / total_doses) * 100.",
    )


# ---------------------------------------------------------------------------
# Doctor Summary Model
# ---------------------------------------------------------------------------
class DoctorSummary(BaseModel):
    """A comprehensive summary designed for sharing with a healthcare provider.

    This model aggregates all relevant patient data into a single document
    that can be printed or shared electronically. It includes:
      - Current active medications with dosages
      - Adherence statistics per medication
      - Recent symptom reports
      - A human-readable summary text

    The summary_text field contains a formatted, natural-language overview
    that a doctor can quickly scan during an appointment.

    ⚕️ MEDICAL DISCLAIMER:
    This summary is generated from self-reported data and is intended to
    SUPPLEMENT — not replace — clinical records. Healthcare providers should
    verify all information with their own records and clinical judgment.
    """

    generated_at: str = Field(
        ...,
        description="ISO-8601 timestamp when this summary was generated.",
    )
    patient_name: str = Field(
        ...,
        description="Name of the patient this summary is for.",
    )
    medications: list[dict] = Field(
        default_factory=list,
        description="List of current active medications with dosage details.",
    )
    adherence_reports: list[AdherenceReport] = Field(
        default_factory=list,
        description="Adherence statistics for each medication.",
    )
    symptoms: list[dict] = Field(
        default_factory=list,
        description="Recent symptom reports within the reporting period.",
    )
    summary_text: str = Field(
        default="",
        description="Human-readable summary suitable for a healthcare provider.",
    )
