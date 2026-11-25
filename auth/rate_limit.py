from collections import defaultdict
from time import monotonic

class LoginRateLimiter:
    def __init__(self, limit=5, window_seconds=300):
        self.limit = limit
        self.window_seconds = window_seconds
        self.events = defaultdict(list)
    def allowed(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        events = [t for t in self.events[key] if t > cutoff]
        self.events[key] = events
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True

login_limiter = LoginRateLimiter()
