"""Persisted profession energy. Screen readings take precedence over estimates."""
from pathlib import Path
import json
import time


class EnergyStore:
    def __init__(self, path):
        self.path = Path(path)
        self.value = None
        self.maximum = 100
        self.estimated = True
        self.pending = 0
        self.updated_at = None
        self.spend_active = False
        self.last_sync = None
        try:
            data = json.loads(self.path.read_text())
            if data.get('version') == 1:
                value, maximum = data.get('value'), data.get('maximum')
                if type(value) is int and type(maximum) is int and 0 <= value <= maximum <= 10000:
                    self.value, self.maximum = value, maximum
                    self.updated_at = data.get('updated_at')
                    self.spend_active = data.get('spend_active') is True
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        # A saved reading is never authoritative for a new game session.

    def sync(self, value, maximum):
        if type(value) is not int or type(maximum) is not int or not 0 <= value <= maximum <= 10000 or not maximum:
            raise ValueError('Geçersiz meslek enerjisi.')
        self.value, self.maximum = value, maximum
        self.estimated = False
        self.pending = 0
        self.last_sync = time.monotonic()
        self.save()

    def manual_completed(self):
        self.pending += 1
        if self.value is not None:
            self.value = min(self.maximum, self.value + 1)
        self.estimated = True
        self.save()

    def needs_sync(self):
        return (self.last_sync is None or self.value is None or self.pending >= 10
                or self.value >= self.maximum or time.monotonic()-self.last_sync >= 180)

    def save(self):
        self.updated_at = time.strftime('%Y-%m-%d %H:%M:%S')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.snapshot() | {'version': 1}, ensure_ascii=False, indent=2))
        temp.replace(self.path)

    def snapshot(self):
        return dict(value=self.value, maximum=self.maximum, estimated=self.estimated,
                    pending=self.pending, updated_at=self.updated_at, spend_active=self.spend_active)
