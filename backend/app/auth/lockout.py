import time
import logging
from collections import defaultdict
from typing import Dict, Tuple

logger = logging.getLogger("hospital.security.lockout")

# In-memory failed attempt tracker: key -> (failed_count, lock_until_timestamp)
_failed_attempts: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes

def is_account_locked(identifier: str) -> Tuple[bool, int]:
    """
    Checks if a staff account or IP address is currently locked out due to brute-force attempts.
    Returns (is_locked, remaining_seconds_locked).
    """
    count, lock_until = _failed_attempts[identifier]
    now = time.time()

    if count >= MAX_FAILED_ATTEMPTS:
        if now < lock_until:
            remaining = int(lock_until - now)
            return True, remaining
        else:
            # Lockout expired, reset counter
            _failed_attempts[identifier] = (0, 0.0)
            return False, 0
    return False, 0

def record_failed_login(identifier: str) -> int:
    """
    Records a failed authentication attempt.
    If threshold is reached, triggers an automated lockout.
    Returns remaining attempts before lockout.
    """
    count, lock_until = _failed_attempts[identifier]
    new_count = count + 1
    now = time.time()

    if new_count >= MAX_FAILED_ATTEMPTS:
        lock_until = now + LOCKOUT_DURATION_SECONDS
        _failed_attempts[identifier] = (new_count, lock_until)
        logger.critical(f"[ACCOUNT LOCKED] Too many failed logins for {identifier}. Locked for {LOCKOUT_DURATION_SECONDS}s.")
        return 0
    else:
        _failed_attempts[identifier] = (new_count, lock_until)
        logger.warning(f"Failed login attempt {new_count}/{MAX_FAILED_ATTEMPTS} for {identifier}")
        return MAX_FAILED_ATTEMPTS - new_count

def reset_failed_login(identifier: str):
    """Clears failed attempts upon successful authentication."""
    if identifier in _failed_attempts:
        del _failed_attempts[identifier]
