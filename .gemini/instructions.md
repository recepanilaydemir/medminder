# MedMinder Development Instructions

## 🧪 Testing Policy (MANDATORY)

### After Every Code Change
1. **Run the full test suite** after any code modification:
   ```bash
   source venv/bin/activate && python -m pytest tests/ -v --tb=short
   ```
2. **Fix any failures** before committing. Do NOT commit code that breaks existing tests.
3. If a test failure is caused by an intentional change, **update the test** to match the new behavior.

### When Adding New Features
1. **Write Gherkin feature files first** in `tests/features/` describing the expected behavior.
2. **Write step definitions** in `tests/step_defs/` implementing the test logic.
3. **Run the new tests** to verify they pass before considering the feature complete.
4. **Update `TESTING.md`** with the new test coverage information.

### Test Structure Rules
- Feature files go in `tests/features/*.feature`
- Step definitions go in `tests/step_defs/test_*.py`
- Each feature file should have a corresponding step definition file
- Use `pytest-bdd` with synchronous step functions (wrap async calls with `asyncio.run()`)
- Each test gets its own isolated temp database via `tmp_path`
- Tests should NOT require an API key or running server (test at DB/MCP level)

### Minimum Coverage Requirements
- All MCP tools must have at least one happy-path test
- All safety-critical logic (dosage validation, duplicate detection) must have edge-case tests
- All new API endpoints must have feature file scenarios (step defs when feasible)

## 📁 Project Structure
- `backend/` — Python server, agents, MCP servers, database
- `frontend/` — Static HTML/CSS/JS served by the backend
- `tests/` — Gherkin BDD tests (see TESTING.md for full coverage)
- `TESTING.md` — Test coverage documentation

## 🔒 Safety-Critical Code
The following areas require extra test diligence:
- `backend/mcp_servers/medminder_server.py` → `add_medication()` tool (safety checks)
- `backend/mcp_servers/medminder_server.py` → `lookup_drug_info()` tool (FDA API)
- `backend/agents/schedule_agent.py` → Dosage validation prompts
- `backend/server.py` → `_get_mcp_source()` (trace attribution)
