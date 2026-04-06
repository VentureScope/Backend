"""
Rate limiting utilities for API endpoints.
"""

import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import HTTPException, status


class RateLimiter:
    """
    Simple in-memory rate limiter using token bucket algorithm.

    For production, will be Redis-based rate limiting.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Store: user_id -> (request_count, window_start_time)
        self._buckets: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))

    def check_rate_limit(self, user_id: str) -> None:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: User ID to check

        Raises:
            HTTPException: 429 Too Many Requests if limit exceeded
        """
        current_time = time.time()
        request_count, window_start = self._buckets[user_id]

        # Check if we're in a new time window
        if current_time - window_start >= self.window_seconds:
            # Reset the window
            self._buckets[user_id] = (1, current_time)
            return

        # We're in the same window
        if request_count >= self.max_requests:
            # Rate limit exceeded
            time_remaining = int(self.window_seconds - (current_time - window_start))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.max_requests} uploads per {self.window_seconds // 60} minutes. Try again in {time_remaining} seconds.",
                headers={"Retry-After": str(time_remaining)},
            )

        # Increment request count
        self._buckets[user_id] = (request_count + 1, window_start)

    def reset(self, user_id: str) -> None:
        """
        Reset rate limit for a specific user.

        Args:
            user_id: User ID to reset
        """
        if user_id in self._buckets:
            del self._buckets[user_id]

    def cleanup_expired(self) -> int:
        """
        Remove expired rate limit entries to prevent memory leaks.
        Should be called periodically.

        Returns:
            Number of entries cleaned up
        """
        current_time = time.time()
        expired_users = [
            user_id
            for user_id, (_, window_start) in self._buckets.items()
            if current_time - window_start >= self.window_seconds
        ]

        for user_id in expired_users:
            del self._buckets[user_id]

        return len(expired_users)


# Global rate limiter instances
# 10 transcript uploads per hour per user
transcript_upload_limiter = RateLimiter(max_requests=10, window_seconds=3600)
