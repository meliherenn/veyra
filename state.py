"""Pure timing/state rules, also used by the offline regression tests."""
from __future__ import annotations
from dataclasses import dataclass

from config import RESUME_CLEAR_FRAMES, RESUME_CLEAR_SECONDS


@dataclass
class ResumeGate:
    latched: bool = False
    first_clear: float | None = None
    clear_frames: int = 0
    seconds: float = RESUME_CLEAR_SECONDS

    def block(self, seconds=None):
        self.latched = True
        self.first_clear = None
        self.clear_frames = 0
        self.seconds = RESUME_CLEAR_SECONDS if seconds is None else float(seconds)

    def update(self, clear, now):
        if not self.latched:
            return True
        if not clear:
            self.first_clear = None
            self.clear_frames = 0
            return False
        if self.first_clear is None:
            self.first_clear = now
        self.clear_frames += 1
        if self.clear_frames >= RESUME_CLEAR_FRAMES and now-self.first_clear >= self.seconds:
            self.latched = False
            return True
        return False


@dataclass
class HarvestTracker:
    started_at: float | None = None
    clear_since: float | None = None
    clear_frames: int = 0
    last_seen_at: float | None = None

    def update(self, harvesting, clear, now):
        if harvesting:
            if self.started_at is None:
                self.started_at = now
            self.clear_since = None
            self.clear_frames = 0
            self.last_seen_at = now
            return False
        if not clear or self.started_at is None:
            self.clear_since = None
            self.clear_frames = 0
            return False
        if self.clear_since is None:
            self.clear_since = now
        self.clear_frames += 1
        return (self.clear_frames >= 2 and now-self.clear_since >= .15
                and now-self.started_at >= 1.5)

    @property
    def measured_seconds(self):
        if self.started_at is None or self.clear_since is None:
            return None
        return self.clear_since-self.started_at

    @property
    def uncertainty(self):
        if self.last_seen_at is None or self.clear_since is None:
            return None
        return max(0,self.clear_since-self.last_seen_at)
