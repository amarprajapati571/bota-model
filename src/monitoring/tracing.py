from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


@contextmanager
def trace_span(name: str) -> Iterator[dict[str, float | str]]:
    span: dict[str, float | str] = {"name": name, "start": perf_counter()}
    try:
        yield span
    finally:
        span["duration_seconds"] = perf_counter() - float(span["start"])
