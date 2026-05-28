"""Login rate limiting to prevent brute force attacks."""

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class LoginAttempt:
    """Track login attempts for an IP."""

    attempts: int = 0
    first_attempt_time: float = 0.0
    locked_until: float = 0.0


class LoginRateLimiter:
    """Rate limiter for login attempts.

    Limits failed login attempts per IP address to prevent brute force attacks.
    After MAX_ATTEMPTS failed attempts, the IP is locked out for LOCKOUT_SECONDS.

    Usage:
        limiter = LoginRateLimiter()

        # Check if IP is allowed to attempt login
        if not limiter.check(ip):
            return JSONResponse(status_code=429, content={"detail": "Too many attempts"})

        # After failed login
        limiter.record_failure(ip)

        # After successful login
        limiter.reset(ip)

        # Get remaining attempts
        remaining = limiter.get_remaining_attempts(ip)
    """

    MAX_ATTEMPTS: int = 5
    LOCKOUT_SECONDS: int = 300  # 5 minutes

    def __init__(self) -> None:
        self._attempts: dict[str, LoginAttempt] = field(default_factory=dict)
        self._lock = Lock()

    def _get_attempt(self, ip: str) -> LoginAttempt:
        """Get or create attempt record for IP."""
        with self._lock:
            if ip not in self._attempts:
                self._attempts[ip] = LoginAttempt()
            return self._attempts[ip]

    def _cleanup_expired(self, ip: str, attempt: LoginAttempt) -> None:
        """Remove expired attempt record."""
        now = time.time()
        if (
            attempt.attempts == 0
            or (attempt.locked_until > 0 and now > attempt.locked_until)
            or (attempt.first_attempt_time > 0 and now - attempt.first_attempt_time > self.LOCKOUT_SECONDS * 2)
        ):
            with self._lock:
                self._attempts.pop(ip, None)

    def check(self, ip: str) -> bool:
        """Check if IP is allowed to attempt login.

        Returns:
            True if IP can attempt login, False if locked out.
        """
        attempt = self._get_attempt(ip)
        self._cleanup_expired(ip, attempt)

        now = time.time()

        # Check if currently locked out
        if attempt.locked_until > now:
            return False

        # Reset if lockout expired
        if attempt.locked_until > 0 and now >= attempt.locked_until:
            attempt.attempts = 0
            attempt.first_attempt_time = 0.0
            attempt.locked_until = 0.0

        return True

    def record_failure(self, ip: str) -> None:
        """Record a failed login attempt for IP.

        Increments attempt counter and applies lockout if threshold reached.
        """
        attempt = self._get_attempt(ip)
        now = time.time()

        # Reset if first attempt was too long ago (outside lockout window)
        if attempt.first_attempt_time > 0 and now - attempt.first_attempt_time > self.LOCKOUT_SECONDS:
            attempt.attempts = 0
            attempt.first_attempt_time = now
        elif attempt.first_attempt_time == 0:
            attempt.first_attempt_time = now

        attempt.attempts += 1

        # Apply lockout if max attempts reached
        if attempt.attempts >= self.MAX_ATTEMPTS:
            attempt.locked_until = now + self.LOCKOUT_SECONDS

    def reset(self, ip: str) -> None:
        """Reset login attempts for IP after successful login."""
        with self._lock:
            self._attempts.pop(ip, None)

    def get_remaining_attempts(self, ip: str) -> int:
        """Get remaining login attempts for IP.

        Returns:
            Number of attempts remaining before lockout.
        """
        attempt = self._get_attempt(ip)
        self._cleanup_expired(ip, attempt)

        now = time.time()
        if attempt.locked_until > now:
            return 0

        return max(0, self.MAX_ATTEMPTS - attempt.attempts)

    def get_lockout_remaining_seconds(self, ip: str) -> int:
        """Get remaining lockout time in seconds.

        Returns:
            Seconds remaining in lockout, or 0 if not locked out.
        """
        attempt = self._get_attempt(ip)
        now = time.time()

        if attempt.locked_until <= now:
            return 0

        return int(attempt.locked_until - now)


# Global singleton instance
_login_limiter: LoginRateLimiter | None = None


def get_login_rate_limiter() -> LoginRateLimiter:
    """Get the global login rate limiter instance."""
    global _login_limiter
    if _login_limiter is None:
        _login_limiter = LoginRateLimiter()
    return _login_limiter
