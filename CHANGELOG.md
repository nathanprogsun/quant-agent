# Changelog

All notable changes to this project will be documented in this file.

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
