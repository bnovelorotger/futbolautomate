from __future__ import annotations

import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def retry(
    attempts: int,
    backoff_seconds: float,
    exceptions: tuple[type[Exception], ...],
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    if attempt == attempts:
                        break
                    time.sleep(backoff_seconds * attempt)
            assert last_error is not None
            raise last_error

        return wrapped

    return decorator

