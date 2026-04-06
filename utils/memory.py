from __future__ import annotations

import tracemalloc
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def memory_profiled() -> Iterator[dict[str, float]]:
    holder = {"delta_mb": 0.0}
    tracemalloc.start()
    before, _ = tracemalloc.get_traced_memory()
    try:
        yield holder
    finally:
        after, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        holder["delta_mb"] = max(0.0, (after - before) / (1024 * 1024))
