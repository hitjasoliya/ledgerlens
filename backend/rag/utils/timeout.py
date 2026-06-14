from __future__ import annotations

import functools
import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TimeoutError(BaseException):
    pass


def timeout_after(seconds: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            result: list[T] = []
            exception: list[BaseException | None] = [None]

            def runner() -> None:
                try:
                    result.append(func(*args, **kwargs))
                except BaseException as e:
                    exception[0] = e

            t = threading.Thread(target=runner, daemon=True)
            t.start()
            t.join(timeout=seconds)
            if t.is_alive():
                raise TimeoutError(
                    f"Function {func.__name__} timed out after {seconds}s"
                )
            if exception[0]:
                raise exception[0]  # type: ignore[misc]
            return result[0]

        return wrapper

    return decorator
