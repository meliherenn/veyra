"""Wall-time spans and event counters for tuning; no game/network data."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import json
import time


class Metrics:
    def __init__(self):
        self.timings: dict[str, list[float]] = {}
        self.counts: Counter = Counter()
        self.started = time.time()
        self._last_save = 0.0
        self._last_ticks = 0
        self._last_save_at_mono = time.monotonic()

    @contextmanager
    def span(self, key):
        start = time.monotonic()
        try:
            yield
        finally:
            self.add(key, time.monotonic() - start)

    def add(self, key, seconds):
        if seconds < 0:
            return
        slot = self.timings.get(key)
        if slot is None:
            slot = self.timings[key] = [0, 0.0, 0.0]
        slot[0] += 1
        slot[1] += seconds
        if seconds > slot[2]:
            slot[2] = seconds

    def bump(self, key, n=1):
        self.counts[key] += n

    def snapshot(self):
        now = time.monotonic()
        ticks = self.counts.get('tick', 0)
        span = max(1e-6, now - self._last_save_at_mono)
        rate = (ticks - self._last_ticks) / span
        return {
            'uptime_seconds': round(time.time() - self.started, 1),
            'ticks': ticks,
            'ticks_per_second': round(rate, 2),
            'timings': {
                key: {
                    'count': int(slot[0]),
                    'avg_ms': round(slot[1] / slot[0] * 1000, 1),
                    'max_ms': round(slot[2] * 1000, 1),
                    'total_s': round(slot[1], 1),
                }
                for key, slot in sorted(self.timings.items())
            },
            'counts': dict(sorted(self.counts.items())),
        }

    def save(self, path, min_interval=5.0, force=False):
        now = time.monotonic()
        if not force and now - self._last_save < min_interval:
            return False
        self._last_save = now
        try:
            data = self.snapshot()
            self._last_ticks = self.counts.get('tick', 0)
            self._last_save_at_mono = now
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            temp.replace(path)
        except OSError:
            return False
        return True


METRICS = Metrics()
