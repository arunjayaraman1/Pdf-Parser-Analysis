from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


@contextmanager
def timed() -> Iterator[dict[str, float]]:
    holder: dict[str, float] = {"seconds": 0.0}
    start = perf_counter()
    try:
        yield holder
    finally:
        holder["seconds"] = perf_counter() - start
