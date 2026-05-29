# DC42 + jqcli Integration — Shared Task Notes

## Task Checklist

- [x] Task 1: jqcli Package Migration
- [x] Task 2: DC42 and Backtest Type Definitions
- [x] Task 3: DC42 Build Pipeline — Steps 01-02 (Ingest + Extract)
- [x] Task 4: DC42 Build Pipeline — Steps 03-05 (LLM Enrichment)
- [x] Task 5: DC42 Build Pipeline — Steps 06-08 (Stats + Embed + Validate)
- [x] Task 6: DC42 Retriever
- [x] Task 7: BacktestService
- [x] Task 8: Backtest API Routes
- [x] Task 9: DC42 Analyzer
- [x] Task 10: Agent Tools (lint_code, validate_parameters)
- [x] Task 11: Frontend — Session State Machine + Backtest SSE
- [x] Task 12: Frontend — Backtest UI Components
- [x] Task 13: Frontend — Settings Pages

## Notes for Next Iteration

- jqcli source package already has api/, commands/, cli.py, config.py, errors.py, output.py
- ApplicationError is abstract (has `http_code` abstractmethod) — BacktestError must implement `http_code()`
- Integration tests use `authed_api_client` fixture (APITestClient), not `client` + `auth_headers` — Task 8 tests need adaptation
- Unit tests use `conftest.py` with `mock_user_service`, `sample_user_dto`, etc.
- Frontend workspace components already exist (InputBox, MessageList, ThreadList, etc.)
