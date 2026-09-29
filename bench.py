"""Offline recognition benchmark over test fixtures; no capture or input.

Usage: .venv/bin/python bench.py [--runs N]
Prints the same timing structure that the live bot writes to runtime/metrics.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from metrics import METRICS
from screen_detector import ScreenDetector

FIXTURES = Path(__file__).resolve().parent / 'tests' / 'fixtures'


def load(name):
    return np.array(Image.open(FIXTURES / name).convert('RGB'))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=3, help='Her görüntü kaç kez işlensin')
    args = parser.parse_args(argv)

    names = sorted(p.name for p in FIXTURES.glob('*.png'))
    if not names:
        print('tests/fixtures altında görüntü yok.')
        return 1

    detector = ScreenDetector()
    rows = []
    try:
        for name in names:
            frame = load(name)
            start = METRICS.timings.get('observe', [0, 0.0, 0.0])[1]
            for _ in range(args.runs):
                obs = detector.observe(frame)
                if obs.clear and obs.layout:
                    detector.find_fish_ripples(frame, obs.layout, 'all')
            elapsed = METRICS.timings.get('observe', [0, 0.0, 0.0])[1] - start
            rows.append((name, elapsed / args.runs, obs.clear))
    finally:
        detector.close()

    snapshot = METRICS.snapshot()
    print(f'{"görüntü":<24} {"observe":>10}   durum')
    for name, seconds, clear in rows:
        print(f'{name:<24} {seconds*1000:>8.1f}ms   {"net" if clear else "engelli"}')
    print()
    print(json.dumps(snapshot['timings'], ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
