# 🧪 MedMinder Test Coverage

> **Framework**: [pytest-bdd](https://pytest-bdd.readthedocs.io/) (Gherkin BDD)  
> **Runner**: `pytest`  
> **Last verified**: 2026-06-23 — **45/45 passing** ✅

---

## Quick Start

```bash
# Run all tests
source venv/bin/activate && python -m pytest tests/ -v

# Run a specific feature area
python -m pytest tests/step_defs/test_medication_safety.py -v

# Run with short traceback on failure
python -m pytest tests/ -v --tb=short

# Run only tests matching a keyword
python -m pytest tests/ -v -k "duplicate"
```

---

## Test Coverage Matrix

### 1. Medication Management (`medication_management.feature`)

Core CRUD operations for medication tracking.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Add a new medication | `add_medication` creates a record in the DB | Unit |
| 2 | Add medication with notes | Notes field persists correctly | Unit |
| 3 | List medications when empty | Empty list returns gracefully | Unit |
| 4 | Remove a medication | `remove_medication` deactivates the record | Unit |
| 5 | Log a taken dose | `log_dose` records "taken" status | Unit |
| 6 | Log a missed dose with reason | `log_missed_dose` records "missed" with reason text | Unit |

**Step definitions**: [`test_medication_management.py`](tests/step_defs/test_medication_management.py)

---

### 2. Medication Safety Checks (`medication_safety.feature`) 🔒

Tool-level safety enforcement — these checks happen **inside the MCP tool**, not via LLM prompts, ensuring they cannot be bypassed.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Warn on exact duplicate | Same name + same times → `duplicate_exact` warning | Unit |
| 2 | Warn on same med, different time | Same name, different times → `duplicate_different_time` | Unit |
| 3 | Warn on similar name | "Metformin" vs "Metformin ER" → `similar_name` | Unit |
| 4 | No false positive for different meds | Different drug name → no duplicate warnings | Unit |
| 5 | FDA label retrieved for known drug | Aspirin → openFDA returns dosage info | Integration |
| 6 | FDA handles unknown drug | Made-up name → `fda_not_found` | Integration |
| 7 | Confirmed add bypasses checks | `confirmed=true` → medication added successfully | Unit |
| 8 | Unconfirmed add blocks | Warnings present → medication NOT in DB | Unit |
| 9 | Case-insensitive duplicates | "metformin" matches "Metformin" | Unit |
| 10 | First medication still checks FDA | No duplicates but FDA check still runs | Integration |

**Step definitions**: [`test_medication_safety.py`](tests/step_defs/test_medication_safety.py)  
**External dependency**: openFDA API (`api.fda.gov`) — free, no key needed

---

### 3. FDA Drug Information Lookup (`fda_drug_lookup.feature`) 💊

Tests the `lookup_drug_info` MCP tool which queries the openFDA Drug Label API.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Look up by generic name | "metformin" → found with generic_name | Integration |
| 2 | Look up by brand name | "Tylenol" → found with brand_name | Integration |
| 3 | Returns dosage forms | "lisinopril" → dosage_forms_and_strengths present | Integration |
| 4 | Returns warnings | "aspirin" → warnings field present | Integration |
| 5 | Includes medical disclaimer | Result contains physician consultation text | Unit |
| 6 | Unknown drug name | "XyzNotARealDrug999" → status "not_found" | Integration |
| 7 | Whitespace-only name | Edge case → handled gracefully, no crash | Integration |
| 8 | Long labels truncated | dosage_and_administration ≤ 1500 chars | Integration |

**Step definitions**: [`test_fda_drug_lookup.py`](tests/step_defs/test_fda_drug_lookup.py)  
**External dependency**: openFDA API (`api.fda.gov`)

---

### 4. MCP Tool Tracing (`mcp_tracing.feature`) 📡

Tests the transparency/explainability system that shows users which MCP servers the agent called.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Trace captures tool_call events | tool_call has tool_name + tool_args | Unit |
| 2 | Trace captures tool_response events | tool_response has tool_name + result_preview | Unit |
| 3 | Trace captures text events | text events have author field | Unit |
| 4 | MedMinder tools attributed | `list_medications` → "MedMinder MCP Server" | Unit |
| 5 | FDA tool attributed | `lookup_drug_info` → "MedMinder MCP → openFDA API" | Unit |
| 6 | Agent router attributed | `transfer_to_agent` → "ADK Agent Router" | Unit |
| 7 | BioMCP tools attributed | `search_drug_interactions` → "BioMCP (DDInter/PubMed)" | Unit |
| 8 | drug-interaction-mcp attributed | `check_interaction` → "drug-interaction-mcp" | Unit |
| 9 | Unknown tools fallback | `some_unknown_tool` → "External MCP" | Unit |
| 10 | Trace summary counts | Counts agents, tools, and total steps | Unit |

**Step definitions**: [`test_mcp_tracing.py`](tests/step_defs/test_mcp_tracing.py)

---

### 5. Medication Reminders (`medication_reminders.feature`) ⏰

Daily schedule generation and completion status tracking.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | View empty schedule | No medications → empty schedule | Unit |
| 2 | View schedule with medications | 2 medications → schedule contains both | Unit |
| 3 | Schedule shows completion | Logged dose → schedule reflects taken status | Unit |

**Step definitions**: [`test_medication_reminders.py`](tests/step_defs/test_medication_reminders.py)

---

### 6. Health Tracking & Reports (`health_tracking.feature`) 📊

Symptom logging, adherence reports, and doctor summary generation.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Log a symptom | `log_symptom` records name + severity | Unit |
| 2 | High-severity warning | Severity 5 → warning included | Unit |
| 3 | Symptom linked to medication | Symptom references a specific medication | Unit |
| 4 | Adherence report (no data) | 0 medications → report shows empty | Unit |
| 5 | Adherence report (with data) | Taken + missed → percentage calculated | Unit |
| 6 | Doctor summary | Includes medications, symptoms, disclaimer | Unit |

**Step definitions**: [`test_health_tracking.py`](tests/step_defs/test_health_tracking.py)

---

### 7. Drug Interactions (`drug_interactions.feature`) ⚠️

Drug-drug interaction checking via external MCP servers.

| # | Scenario | What It Tests | Type |
|---|----------|--------------|------|
| 1 | Interaction data returned | Warfarin + Aspirin → interaction data + disclaimer | Integration |
| 2 | No interaction found | Metformin + Acetaminophen → no significant interaction | Integration |

**Step definitions**: [`test_drug_interactions.py`](tests/step_defs/test_drug_interactions.py)

---

### 8. Agent Routing (`agent_routing.feature`) 🔀 — *Feature only*

Multi-agent orchestration and message routing. 14 scenarios covering routing to ScheduleAgent, InteractionAgent, HealthAgent, direct orchestrator handling, medical disclaimers, and emergency protocols.

> **Status**: Feature file written. Step definitions require a running agent with API key — suitable for integration/E2E testing.

---

### 9. REST API Endpoints (`api_endpoints.feature`) 🌐 — *Feature only*

HTTP API coverage including chat, config, medications, schedule, static files, error handling, and session persistence. 16 scenarios.

> **Status**: Feature file written. Step definitions require a running server — suitable for integration/E2E testing.

---

## Coverage Summary

```
Feature Area                  Scenarios   Step Defs   Status
─────────────────────────────────────────────────────────────
Medication Management              6         ✅        PASSING
Medication Safety Checks          10         ✅        PASSING
FDA Drug Lookup                    8         ✅        PASSING
MCP Tool Tracing                  10         ✅        PASSING
Medication Reminders               3         ✅        PASSING
Health Tracking & Reports          6         ✅        PASSING
Drug Interactions                  2         ✅        PASSING
Agent Routing                     14         📝        FEATURE ONLY
REST API Endpoints                16         📝        FEATURE ONLY
─────────────────────────────────────────────────────────────
TOTAL                             75         45/75     45 PASSING
```

---

## Architecture

```
tests/
├── conftest.py                    # Shared fixtures (test DB, mock agent, etc.)
├── features/                      # Gherkin .feature files (human-readable)
│   ├── medication_management.feature
│   ├── medication_safety.feature
│   ├── fda_drug_lookup.feature
│   ├── mcp_tracing.feature
│   ├── medication_reminders.feature
│   ├── health_tracking.feature
│   ├── drug_interactions.feature
│   ├── agent_routing.feature      # Feature only (needs live agent)
│   └── api_endpoints.feature      # Feature only (needs live server)
└── step_defs/                     # Python step definitions
    ├── test_medication_management.py
    ├── test_medication_safety.py
    ├── test_fda_drug_lookup.py
    ├── test_mcp_tracing.py
    ├── test_medication_reminders.py
    ├── test_health_tracking.py
    └── test_drug_interactions.py
```

### Test Design Principles

1. **Database isolation**: Each test gets its own temporary SQLite DB via `tmp_path`
2. **No API key needed**: Tests bypass the LLM agent and test the DB/MCP layers directly
3. **Real external calls**: FDA tests hit `api.fda.gov` for authentic validation (free, no key)
4. **Tool-level testing**: Safety checks are tested at the MCP tool level, not the prompt level, because prompts can be ignored by the LLM

---

## Adding New Tests

When adding a new feature, follow this process:

### 1. Write the feature file first

```gherkin
# tests/features/my_new_feature.feature
Feature: My New Feature
  As a patient
  I want [capability]
  So that [benefit]

  Scenario: Happy path
    Given [precondition]
    When [action]
    Then [expected result]
```

### 2. Create step definitions

```python
# tests/step_defs/test_my_new_feature.py
from pytest_bdd import scenarios, given, when, then, parsers
scenarios("../features/my_new_feature.feature")

@given("...")
def given_step():
    pass

@when("...")
def when_step():
    pass

@then("...")
def then_step():
    pass
```

### 3. Run and verify

```bash
python -m pytest tests/step_defs/test_my_new_feature.py -v --tb=short
```

### 4. Run the full suite to check for regressions

```bash
python -m pytest tests/ -v
```
