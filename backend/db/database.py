"""
MedMinder Database Manager
===========================

Async SQLite database layer for the MedMinder medication tracking system.
Uses `aiosqlite` for non-blocking database operations, which is essential
because the MCP server runs in an asyncio event loop — blocking DB calls
would freeze the entire server.

Architecture Decisions:
  - **SQLite over PostgreSQL**: For a personal health tracker, SQLite provides
    zero-configuration deployment, single-file portability, and sufficient
    performance for single-user workloads. The DB file can be backed up by
    simply copying it.
  - **aiosqlite**: Wraps sqlite3 in a thread executor so DB operations don't
    block the asyncio event loop. This is critical for MCP server responsiveness.
  - **UUID4 primary keys**: Avoid auto-increment collisions if the DB is ever
    merged or migrated. UUIDs are stored as TEXT in SQLite.
  - **Soft deletion for medications**: Setting `active = 0` instead of DELETE
    preserves dose log history for accurate adherence reporting.
  - **ISO-8601 timestamps**: Stored as TEXT for SQLite compatibility and
    human readability in the raw database file.

⚕️ MEDICAL DISCLAIMER:
  This database stores self-reported health data for informational purposes.
  It is NOT a certified medical record system and should NOT be used as the
  sole basis for medical decisions. Always consult a healthcare professional.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import aiosqlite

from .models import (
    AdherenceReport,
    DoctorSummary,
    DoseLog,
    Medication,
    Symptom,
    User,
)

# Configure module-level logger so issues are traceable
logger = logging.getLogger(__name__)


class MedMinderDB:
    """Async database manager for MedMinder.

    This class encapsulates all database operations behind a clean async API.
    Each public method:
      1. Opens a connection (aiosqlite handles connection pooling internally)
      2. Executes the query with parameterized SQL (prevents SQL injection)
      3. Returns a validated Pydantic model

    Usage::

        db = MedMinderDB("medminder.db")
        await db.init_db()
        med = await db.add_medication("user1", "Aspirin", "100mg", "daily", ["08:00"])
    """

    def __init__(self, db_path: str = "medminder.db") -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file. The file will be
                     created automatically if it doesn't exist. Defaults to
                     'medminder.db' in the current working directory.
        """
        self.db_path = db_path
        logger.info("MedMinderDB initialized with database path: %s", db_path)

    # ------------------------------------------------------------------
    # Database Initialization
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Create all required tables if they don't already exist.

        Table design notes:
          - `medications.times` stores a JSON array of time strings because
            SQLite doesn't support array columns. We serialize/deserialize
            with json.dumps/json.loads.
          - `dose_logs.status` uses a CHECK constraint as a database-level
            safeguard in addition to Pydantic's Literal type validation.
          - `symptoms.severity` has a CHECK constraint for range 1-5.
          - Foreign keys are enabled explicitly (SQLite has them off by default).

        This method is idempotent — safe to call multiple times.
        """
        logger.info("Initializing database tables...")

        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key enforcement (SQLite disables by default!)
            await db.execute("PRAGMA foreign_keys = ON")

            # ── Users Table ──────────────────────────────────────────
            # Minimal user records — MedMinder is not an auth system.
            # The user_id comes from the external system (LLM session, etc.)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # ── Medications Table ────────────────────────────────────
            # `times` is stored as a JSON string (e.g., '["08:00","20:00"]')
            # `active` is an integer 0/1 (SQLite boolean convention)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS medications (
                    id         TEXT PRIMARY KEY,
                    user_id    TEXT NOT NULL,
                    name       TEXT NOT NULL,
                    dosage     TEXT NOT NULL,
                    frequency  TEXT NOT NULL,
                    times      TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    active     INTEGER NOT NULL DEFAULT 1,
                    notes      TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # ── Dose Logs Table ──────────────────────────────────────
            # Records each dose event. The CHECK constraint on status
            # provides a database-level safety net.
            await db.execute("""
                CREATE TABLE IF NOT EXISTS dose_logs (
                    id             TEXT PRIMARY KEY,
                    medication_id  TEXT NOT NULL,
                    timestamp      TEXT NOT NULL DEFAULT (datetime('now')),
                    status         TEXT NOT NULL CHECK (status IN ('taken', 'missed', 'late')),
                    notes          TEXT,
                    FOREIGN KEY (medication_id) REFERENCES medications(id)
                )
            """)

            # ── Symptoms Table ───────────────────────────────────────
            # Symptom tracking for side-effect correlation.
            # severity CHECK constraint mirrors the Pydantic validator.
            await db.execute("""
                CREATE TABLE IF NOT EXISTS symptoms (
                    id                  TEXT PRIMARY KEY,
                    user_id             TEXT NOT NULL,
                    timestamp           TEXT NOT NULL DEFAULT (datetime('now')),
                    description         TEXT NOT NULL,
                    severity            INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
                    related_medication  TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # ── Indexes ─────────────────────────────────────────────
            # These indexes accelerate the most common query patterns:
            # - Listing medications for a user (filtered by active status)
            # - Querying dose logs for a medication within a date range
            # - Fetching recent symptoms for a user
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_medications_user_active
                ON medications(user_id, active)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_dose_logs_medication_timestamp
                ON dose_logs(medication_id, timestamp)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_symptoms_user_timestamp
                ON symptoms(user_id, timestamp)
            """)

            await db.commit()

        logger.info("Database tables initialized successfully.")

    # ------------------------------------------------------------------
    # User Management
    # ------------------------------------------------------------------

    async def get_or_create_user(self, user_id: str, name: str) -> User:
        """Retrieve an existing user or create a new one.

        This uses an INSERT OR IGNORE pattern — if the user_id already exists,
        the INSERT is silently skipped and we SELECT the existing record.
        This is idempotent and safe for concurrent calls.

        Args:
            user_id: Unique identifier for the user.
            name: Display name for the user.

        Returns:
            User model instance.
        """
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")

            # INSERT OR IGNORE: if user_id PK already exists, this is a no-op
            await db.execute(
                "INSERT OR IGNORE INTO users (id, name, created_at) VALUES (?, ?, ?)",
                (user_id, name, now),
            )
            await db.commit()

            # Always SELECT to get the canonical record (may have been created
            # earlier with a different name — we don't overwrite)
            cursor = await db.execute(
                "SELECT id, name, created_at FROM users WHERE id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            # This should never happen given the INSERT OR IGNORE above,
            # but we handle it defensively
            raise RuntimeError(f"Failed to get or create user with id '{user_id}'")

        return User(id=row[0], name=row[1], created_at=row[2])

    # ------------------------------------------------------------------
    # Medication CRUD
    # ------------------------------------------------------------------

    async def add_medication(
        self,
        user_id: str,
        name: str,
        dosage: str,
        frequency: str,
        times: list[str],
        notes: Optional[str] = None,
    ) -> Medication:
        """Add a new medication to a user's regimen.

        Generates a UUID4 for the medication ID and stores the `times` list
        as a JSON string in SQLite. Also ensures the user exists via
        get_or_create_user (using user_id as both id and name if the user
        doesn't exist yet).

        Args:
            user_id: ID of the user adding this medication.
            name: Medication name (e.g., 'Lisinopril').
            dosage: Dosage string (e.g., '10mg').
            frequency: Frequency description (e.g., 'twice daily').
            times: List of scheduled times in HH:MM format.
            notes: Optional notes about the medication.

        Returns:
            The newly created Medication model instance.
        """
        med_id = str(uuid4())
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Serialize times list to JSON for SQLite TEXT column storage
        times_json = json.dumps(times)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")

            # Ensure the user exists before inserting the medication
            # (foreign key constraint would fail otherwise)
            await db.execute(
                "INSERT OR IGNORE INTO users (id, name, created_at) VALUES (?, ?, ?)",
                (user_id, user_id, datetime.now(timezone.utc).isoformat()),
            )

            await db.execute(
                """INSERT INTO medications
                   (id, user_id, name, dosage, frequency, times, start_date, active, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (med_id, user_id, name, dosage, frequency, times_json, start_date, notes),
            )
            await db.commit()

        logger.info("Added medication '%s' (id=%s) for user '%s'", name, med_id, user_id)

        return Medication(
            id=med_id,
            user_id=user_id,
            name=name,
            dosage=dosage,
            frequency=frequency,
            times=times,
            start_date=start_date,
            active=True,
            notes=notes,
        )

    async def remove_medication(self, medication_id: str) -> bool:
        """Soft-delete a medication by setting active = 0.

        We use soft deletion to preserve historical dose log data. Hard
        deletion would cascade and destroy adherence history, making it
        impossible to generate accurate past reports.

        Args:
            medication_id: UUID of the medication to deactivate.

        Returns:
            True if a medication was found and deactivated, False otherwise.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE medications SET active = 0 WHERE id = ? AND active = 1",
                (medication_id,),
            )
            await db.commit()
            rows_affected = cursor.rowcount

        if rows_affected > 0:
            logger.info("Deactivated medication id=%s", medication_id)
            return True
        else:
            logger.warning(
                "No active medication found with id=%s to deactivate", medication_id
            )
            return False

    async def list_medications(self, user_id: str) -> list[Medication]:
        """List all active medications for a user.

        Only returns medications where active = 1. Inactive (soft-deleted)
        medications are excluded from the list but remain in the database
        for historical reporting.

        Args:
            user_id: ID of the user whose medications to list.

        Returns:
            List of active Medication model instances.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, user_id, name, dosage, frequency, times,
                          start_date, active, notes
                   FROM medications
                   WHERE user_id = ? AND active = 1
                   ORDER BY name""",
                (user_id,),
            )
            rows = await cursor.fetchall()

        medications: list[Medication] = []
        for row in rows:
            medications.append(
                Medication(
                    id=row[0],
                    user_id=row[1],
                    name=row[2],
                    dosage=row[3],
                    frequency=row[4],
                    # Deserialize JSON string back to list
                    times=json.loads(row[5]),
                    start_date=row[6],
                    active=bool(row[7]),
                    notes=row[8],
                )
            )

        logger.info("Listed %d active medications for user '%s'", len(medications), user_id)
        return medications

    # ------------------------------------------------------------------
    # Dose Logging
    # ------------------------------------------------------------------

    async def log_dose(
        self,
        medication_id: str,
        status: str = "taken",
        notes: Optional[str] = None,
    ) -> DoseLog:
        """Record a dose event (taken, missed, or late).

        Each call creates a new DoseLog entry with a UTC timestamp. The
        status must be one of 'taken', 'missed', or 'late' — this is
        validated at both the Pydantic model level and the database CHECK
        constraint level (defense in depth).

        Args:
            medication_id: UUID of the medication this dose is for.
            status: One of 'taken', 'missed', or 'late'.
            notes: Optional notes about the dose event.

        Returns:
            The newly created DoseLog model instance.

        Raises:
            ValueError: If status is not a valid option.
            aiosqlite.IntegrityError: If medication_id doesn't exist.
        """
        # Validate status before hitting the database
        valid_statuses = {"taken", "missed", "late"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid dose status '{status}'. Must be one of: {valid_statuses}"
            )

        log_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """INSERT INTO dose_logs (id, medication_id, timestamp, status, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (log_id, medication_id, timestamp, status, notes),
            )
            await db.commit()

        logger.info(
            "Logged dose: medication_id=%s, status=%s", medication_id, status
        )

        return DoseLog(
            id=log_id,
            medication_id=medication_id,
            timestamp=timestamp,
            status=status,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Symptom Tracking
    # ------------------------------------------------------------------

    async def log_symptom(
        self,
        user_id: str,
        description: str,
        severity: int,
        related_medication: Optional[str] = None,
    ) -> Symptom:
        """Record a symptom reported by the user.

        Symptoms can optionally be linked to a medication name for
        side-effect correlation. The severity scale is:
          1=minimal, 2=mild, 3=moderate, 4=severe, 5=emergency

        Args:
            user_id: ID of the user reporting the symptom.
            description: Description of the symptom.
            severity: Severity rating (1-5).
            related_medication: Optional medication name suspected to cause it.

        Returns:
            The newly created Symptom model instance.

        Raises:
            ValueError: If severity is outside 1-5 range.
        """
        if not 1 <= severity <= 5:
            raise ValueError(
                f"Severity must be between 1 and 5, got {severity}"
            )

        symptom_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")

            # Ensure the user exists
            await db.execute(
                "INSERT OR IGNORE INTO users (id, name, created_at) VALUES (?, ?, ?)",
                (user_id, user_id, timestamp),
            )

            await db.execute(
                """INSERT INTO symptoms
                   (id, user_id, timestamp, description, severity, related_medication)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (symptom_id, user_id, timestamp, description, severity, related_medication),
            )
            await db.commit()

        logger.info(
            "Logged symptom for user '%s': %s (severity=%d)",
            user_id,
            description,
            severity,
        )

        return Symptom(
            id=symptom_id,
            user_id=user_id,
            timestamp=timestamp,
            description=description,
            severity=severity,
            related_medication=related_medication,
        )

    # ------------------------------------------------------------------
    # Reporting & Analytics
    # ------------------------------------------------------------------

    async def get_adherence_report(
        self, user_id: str, days: int = 30
    ) -> list[AdherenceReport]:
        """Generate adherence statistics for each active medication.

        Calculates taken/missed/late counts from dose_logs within the
        specified time window. Adherence percentage is computed as:

            adherence_percentage = (taken / total_doses) * 100

        where total_doses = taken + missed + late.

        Note: If a medication has zero dose logs, it will show 0% adherence
        with total_doses = 0. This is intentional — no logs means no
        confirmed doses.

        Args:
            user_id: ID of the user to generate the report for.
            days: Number of days to look back (default: 30).

        Returns:
            List of AdherenceReport instances, one per active medication.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # Join medications with dose_logs, aggregating by medication
            # LEFT JOIN ensures medications with no logs still appear
            cursor = await db.execute(
                """
                SELECT
                    m.name,
                    COUNT(d.id) AS total_doses,
                    SUM(CASE WHEN d.status = 'taken' THEN 1 ELSE 0 END) AS taken,
                    SUM(CASE WHEN d.status = 'missed' THEN 1 ELSE 0 END) AS missed,
                    SUM(CASE WHEN d.status = 'late' THEN 1 ELSE 0 END) AS late
                FROM medications m
                LEFT JOIN dose_logs d
                    ON m.id = d.medication_id AND d.timestamp >= ?
                WHERE m.user_id = ? AND m.active = 1
                GROUP BY m.id, m.name
                ORDER BY m.name
                """,
                (cutoff, user_id),
            )
            rows = await cursor.fetchall()

        reports: list[AdherenceReport] = []
        for row in rows:
            med_name = row[0]
            total = row[1] or 0
            taken = row[2] or 0
            missed = row[3] or 0
            late = row[4] or 0

            # Calculate adherence percentage (guard against division by zero)
            adherence_pct = (taken / total * 100.0) if total > 0 else 0.0

            reports.append(
                AdherenceReport(
                    medication_name=med_name,
                    total_doses=total,
                    taken=taken,
                    missed=missed,
                    late=late,
                    adherence_percentage=round(adherence_pct, 1),
                )
            )

        logger.info(
            "Generated adherence report for user '%s' (%d days, %d medications)",
            user_id,
            days,
            len(reports),
        )
        return reports

    async def get_symptom_history(
        self, user_id: str, days: int = 30
    ) -> list[Symptom]:
        """Retrieve recent symptom history for a user.

        Returns symptoms ordered by timestamp (most recent first) within
        the specified time window. This data is useful for:
          - Identifying patterns (e.g., headaches every morning)
          - Correlating symptoms with medication changes
          - Sharing symptom timeline with healthcare providers

        Args:
            user_id: ID of the user.
            days: Number of days to look back (default: 30).

        Returns:
            List of Symptom model instances, most recent first.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, user_id, timestamp, description, severity, related_medication
                   FROM symptoms
                   WHERE user_id = ? AND timestamp >= ?
                   ORDER BY timestamp DESC""",
                (user_id, cutoff),
            )
            rows = await cursor.fetchall()

        symptoms = [
            Symptom(
                id=row[0],
                user_id=row[1],
                timestamp=row[2],
                description=row[3],
                severity=row[4],
                related_medication=row[5],
            )
            for row in rows
        ]

        logger.info(
            "Retrieved %d symptoms for user '%s' (last %d days)",
            len(symptoms),
            user_id,
            days,
        )
        return symptoms

    async def get_todays_schedule(self, user_id: str) -> list[dict]:
        """Get today's medication schedule with dose completion status.

        For each active medication, returns:
          - medication name, dosage, and scheduled times
          - whether each scheduled time has a corresponding dose log today

        This powers the "daily view" in the UI, showing the user which
        doses they've taken and which are still pending.

        Args:
            user_id: ID of the user.

        Returns:
            List of dicts with schedule info and completion status.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            # Step 1: Get all active medications for the user
            cursor = await db.execute(
                """SELECT id, name, dosage, times
                   FROM medications
                   WHERE user_id = ? AND active = 1
                   ORDER BY name""",
                (user_id,),
            )
            med_rows = await cursor.fetchall()

            schedule: list[dict] = []
            for row in med_rows:
                med_id, med_name, dosage, times_json = row
                times = json.loads(times_json)

                # Step 2: Count today's dose logs for this medication
                # We check if a dose was logged today (any status counts as "addressed")
                log_cursor = await db.execute(
                    """SELECT COUNT(*) FROM dose_logs
                       WHERE medication_id = ? AND timestamp LIKE ?""",
                    (med_id, f"{today}%"),
                )
                log_count_row = await log_cursor.fetchone()
                doses_logged_today = log_count_row[0] if log_count_row else 0

                schedule.append(
                    {
                        "medication_id": med_id,
                        "medication_name": med_name,
                        "dosage": dosage,
                        "scheduled_times": times,
                        "total_doses_today": len(times),
                        "doses_logged_today": doses_logged_today,
                        "all_taken": doses_logged_today >= len(times),
                    }
                )

        logger.info(
            "Retrieved today's schedule for user '%s': %d medications",
            user_id,
            len(schedule),
        )
        return schedule

    async def generate_doctor_summary(
        self,
        user_id: str,
        patient_name: str = "Patient",
        days: int = 30,
    ) -> DoctorSummary:
        """Generate a comprehensive summary for sharing with a healthcare provider.

        This is the highest-level reporting method. It aggregates:
          1. All active medications with dosage details
          2. Adherence statistics per medication
          3. Recent symptom reports
          4. A formatted natural-language summary

        The summary_text is designed to be scannable during a medical
        appointment — key metrics are highlighted and organized logically.

        Args:
            user_id: ID of the user/patient.
            patient_name: Display name for the report header.
            days: Reporting period in days (default: 30).

        Returns:
            DoctorSummary model instance with all aggregated data.

        ⚕️ MEDICAL DISCLAIMER:
            This summary is generated from self-reported data and should
            be verified against clinical records by the healthcare provider.
        """
        generated_at = datetime.now(timezone.utc).isoformat()

        # Gather all component data concurrently-friendly (sequential here
        # since we're using the same connection pool pattern)
        medications = await self.list_medications(user_id)
        adherence_reports = await self.get_adherence_report(user_id, days)
        symptoms = await self.get_symptom_history(user_id, days)

        # ── Build the formatted summary text ─────────────────────────
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("  MEDMINDER — PATIENT MEDICATION SUMMARY")
        lines.append("=" * 60)
        lines.append(f"  Patient: {patient_name}")
        lines.append(f"  Report Period: Last {days} days")
        lines.append(f"  Generated: {generated_at}")
        lines.append("")

        # ── Current Medications Section ──────────────────────────────
        lines.append("─" * 60)
        lines.append("  CURRENT MEDICATIONS")
        lines.append("─" * 60)
        if medications:
            for med in medications:
                lines.append(f"  • {med.name} — {med.dosage} ({med.frequency})")
                lines.append(f"    Schedule: {', '.join(med.times)}")
                if med.notes:
                    lines.append(f"    Notes: {med.notes}")
        else:
            lines.append("  No active medications on record.")
        lines.append("")

        # ── Adherence Report Section ─────────────────────────────────
        lines.append("─" * 60)
        lines.append("  ADHERENCE SUMMARY")
        lines.append("─" * 60)
        if adherence_reports:
            for report in adherence_reports:
                lines.append(f"  • {report.medication_name}")
                lines.append(
                    f"    Adherence: {report.adherence_percentage}% "
                    f"({report.taken}/{report.total_doses} doses on time)"
                )
                if report.late > 0:
                    lines.append(f"    Late doses: {report.late}")
                if report.missed > 0:
                    lines.append(f"    Missed doses: {report.missed}")
        else:
            lines.append("  No dose data recorded in this period.")
        lines.append("")

        # ── Symptoms Section ─────────────────────────────────────────
        lines.append("─" * 60)
        lines.append("  REPORTED SYMPTOMS")
        lines.append("─" * 60)
        if symptoms:
            severity_labels = {
                1: "Minimal",
                2: "Mild",
                3: "Moderate",
                4: "Severe",
                5: "Emergency",
            }
            for s in symptoms:
                sev_label = severity_labels.get(s.severity, f"Level {s.severity}")
                lines.append(f"  • [{sev_label}] {s.description}")
                lines.append(f"    Reported: {s.timestamp}")
                if s.related_medication:
                    lines.append(f"    Possibly related to: {s.related_medication}")
        else:
            lines.append("  No symptoms reported in this period.")
        lines.append("")

        # ── Footer / Disclaimer ──────────────────────────────────────
        lines.append("─" * 60)
        lines.append("  ⚕️ DISCLAIMER: This report is based on self-reported")
        lines.append("  data and is NOT a substitute for clinical records.")
        lines.append("  Please verify all information with clinical judgment.")
        lines.append("=" * 60)

        summary_text = "\n".join(lines)

        # Build serializable dicts for the model
        med_dicts = [
            {
                "name": m.name,
                "dosage": m.dosage,
                "frequency": m.frequency,
                "times": m.times,
                "notes": m.notes,
            }
            for m in medications
        ]
        symptom_dicts = [
            {
                "description": s.description,
                "severity": s.severity,
                "timestamp": s.timestamp,
                "related_medication": s.related_medication,
            }
            for s in symptoms
        ]

        logger.info(
            "Generated doctor summary for user '%s' (patient: %s, %d days)",
            user_id,
            patient_name,
            days,
        )

        return DoctorSummary(
            generated_at=generated_at,
            patient_name=patient_name,
            medications=med_dicts,
            adherence_reports=adherence_reports,
            symptoms=symptom_dicts,
            summary_text=summary_text,
        )
