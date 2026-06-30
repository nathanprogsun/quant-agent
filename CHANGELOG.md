# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-06-30

### Added
- JoinQuant username/password login with in-memory credential caching (`jqcli_auth.py`)
- `BacktestRegistry` for cross-request ownership tracking (submit → SSE stream agreement)
- Next.js API proxy for `GET /api/v1/backtest/[id]` (fixes 404 on backtest detail fetch)
- Backtest result parsing: trades, holdings, and performance series from jqcli log output

### Changed
- `BacktestService` factory moved from `views.py` to `lifespan_service.py` (`backtest_service_from_request`), consistent with all other service factories
- `resolve_jqcli_credentials` raises `JqcliNotConfiguredError` when unconfigured, eliminating redundant `has_jqcli_configuration` checks across three call sites
- Backtest auth-check endpoint returns three-state response (unconfigured / login-failed / authenticated)
- Frontend backtest UI components refactored (BacktestButton, RunLogPanel, WorkspaceHeader)

### Removed
- `JQCLI_TOKEN` / `JQCLI_COOKIE` environment variables (replaced by `JQCLI_USERNAME` / `JQCLI_PASSWORD`)
- `get_backtest_service`, `_get_app_context`, `get_jqcli_credentials` from `views.py` (consolidated into `lifespan_service.py`)

## [0.1.2] - 2026-05-30

### Added
- `token_version` field to User model for JWT invalidation on password change
- `update_token_version()` method in UserService

### Changed
- JWT tokens now include `ver` field containing user's `token_version`
- Token validation in `get_current_user` dependency checks `token_version` match
- Password change endpoint increments `token_version` and re-issues token with new version

### Removed
- `/api/v1/auth/refresh` endpoint (not needed in cookie-based auth)
- CSRF cookie and `validate_csrf` function (redundant with HttpOnly cookies)
- `csrf_token` field from `ChangePasswordRequest`
- `CSRFResponse` model
