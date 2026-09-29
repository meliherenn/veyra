"""Passive diagnosis of the pre-click reacquire guard; capture only, no input.

Selects a fish ring in memory, waits the time a real cursor travel takes, then
runs exactly the two attempts `fresh_guard` performs. Failures are classified
(ring unseen / centre displaced / fish gone) and followed for a short while to
see whether the ring comes back where it was. Nothing is clicked, scrolled or
typed; ydotool is never called.

Usage:
  .venv/bin/python probe_reacquire.py [--seconds 60] [--travel 0.30]
                                      [--max-saves 10] [--out runtime/reacquire-probe]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

import config
from config import TARGET_REACQUIRE_DISTANCE
from metrics import METRICS
from screen_detector import ScreenDetector

FOLLOW_SECONDS = 1.2
FOLLOW_STEP = 0.15
SELECT_HALF = 120


def nearest_distance(ripples, target):
    if not ripples:
        return None
    fish = min(ripples, key=lambda r: np.hypot(r.x - target.x, r.y - target.y))
    return float(np.hypot(fish.x - target.x, fish.y - target.y))


def save_crop(frame, x, y, path, mark=None):
    y1, y2 = max(0, y - SELECT_HALF), min(frame.shape[0], y + SELECT_HALF)
    x1, x2 = max(0, x - SELECT_HALF), min(frame.shape[1], x + SELECT_HALF)
    crop = frame[y1:y2, x1:x2].copy()
    if mark is not None:
        cv2.circle(crop, (int(x - x1), int(y - y1)), int(mark), (255, 60, 60), 1)
    cv2.imwrite(str(path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=60.0)
    parser.add_argument('--travel', type=float, default=0.30,
                        help='Fare yolculuğu süresi; koruma bu süre sonunda çalışır')
    parser.add_argument('--max-saves', type=int, default=10)
    parser.add_argument('--retry-delay', type=float, default=None,
                        help='Denemeler arası bekleme; verilirse config değerini ezer')
    parser.add_argument('--attempts', type=int, default=None,
                        help='Kaç yeniden-yakalama denemesi; verilirse config değerini ezer')
    parser.add_argument('--out', default='runtime/reacquire-probe')
    args = parser.parse_args(argv)

    retry_delay = config.REACQUIRE_RETRY_DELAY if args.retry_delay is None else args.retry_delay
    attempts = config.REACQUIRE_ATTEMPTS if args.attempts is None else args.attempts

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    detector = ScreenDetector()
    successes, failures, blocked = [], [], 0
    follow_counts = {'animasyon': 0, 'hareket': 0, 'kayip': 0}
    guard_classes = {'halka_yok': 0, 'kayma': 0, 'uzak': 0}
    started = time.monotonic()
    last_target, saved = None, 0
    no_ring_ticks = 0

    try:
        while time.monotonic() - started < args.seconds:
            frame = detector.capture()
            obs = detector.observe(frame)
            if not obs.clear or obs.layout is None:
                blocked += 1
                continue
            ripples = detector.find_fish_ripples(frame, obs.layout, 'all')
            if not ripples:
                no_ring_ticks += 1
                continue

            candidates = [r for r in ripples if last_target is None or
                          np.hypot(r.x - last_target.x, r.y - last_target.y) >= 40]
            target = (candidates or ripples)[0]
            last_target = target
            select_frame = frame
            accept = max(6, target.radius * .6)
            scale = max(.5, obs.layout.width / 1520)
            limit = max(24.0, TARGET_REACQUIRE_DISTANCE * scale)

            time.sleep(args.travel)
            frame = detector.capture()
            obs = detector.observe(frame)
            if not obs.clear or obs.layout is None:
                blocked += 1
                continue

            fresh = None
            for attempt in range(attempts):
                if attempt:
                    METRICS.bump('probe_retry')
                    time.sleep(retry_delay)
                    frame = detector.capture()
                    obs = detector.observe(frame)
                    if not obs.clear or obs.layout is None:
                        blocked += 1
                        break
                fresh = detector.reacquire_fish(frame, obs.layout, target)
                if fresh is not None:
                    break

            if fresh is not None:
                successes.append({'distance': float(np.hypot(fresh.x - target.x, fresh.y - target.y)),
                                  'accept': float(accept), 'radius': int(target.radius)})
                continue

            same = detector.find_fish_ripples(frame, obs.layout, target_color=target.color) \
                if obs.layout else []
            distance = nearest_distance(same, target)
            if distance is None:
                guard_class = 'halka_yok'
            elif distance <= limit:
                guard_class = 'kayma'
            else:
                guard_class = 'uzak'
            guard_classes[guard_class] += 1

            # Follow the dropped target: does the ring come back where it was?
            outcome, seen_far = 'kayip', None
            follow_started = time.monotonic()
            follow_seconds = None
            deadline = follow_started + FOLLOW_SECONDS
            while time.monotonic() < deadline:
                time.sleep(FOLLOW_STEP)
                probe = detector.capture()
                probe_obs = detector.observe(probe)
                if not probe_obs.clear or probe_obs.layout is None:
                    continue
                found = detector.find_fish_ripples(probe, probe_obs.layout,
                                                   target_color=target.color)
                d = nearest_distance(found, target)
                if d is None:
                    continue
                if d <= accept:
                    outcome = 'animasyon'
                    follow_seconds = round(time.monotonic() - follow_started, 2)
                    break
                if seen_far is None or d < seen_far:
                    seen_far = d
            if outcome != 'animasyon':
                outcome = 'hareket' if seen_far is not None else 'kayip'
            follow_counts[outcome] += 1

            record = {'x': int(target.x), 'y': int(target.y), 'color': target.color,
                      'radius': int(target.radius), 'guard_class': guard_class,
                      'guard_distance': None if distance is None else round(distance, 1),
                      'follow': outcome, 'follow_seconds': follow_seconds,
                      'limit': round(limit, 1), 'accept': round(accept, 1)}
            failures.append(record)
            if saved < args.max_saves:
                save_crop(select_frame, target.x, target.y, out / f'fail-{saved:02d}-select.png',
                          mark=accept)
                save_crop(frame, target.x, target.y, out / f'fail-{saved:02d}-guard.png',
                          mark=accept)
                saved += 1
    finally:
        detector.close()

    accepted = sorted(s['distance'] for s in successes)
    def pct(values, p):
        return values[int(len(values) * p)] if values else float('nan')

    follow_times = sorted(f['follow_seconds'] for f in failures
                          if f.get('follow_seconds') is not None)
    summary = {
        'seconds': round(time.monotonic() - started, 1),
        'travel_seconds': args.travel,
        'retry_delay': retry_delay,
        'attempts': attempts,
        'episodes': len(successes) + len(failures),
        'successes': len(successes),
        'failures': len(failures),
        'failure_rate': round(len(failures) / max(1, len(successes) + len(failures)), 3),
        'blocked_ticks': blocked,
        'no_ring_ticks': no_ring_ticks,
        'guard_classes': guard_classes,
        'follow': follow_counts,
        'follow_seconds': {'p50': pct(follow_times, .5), 'max': follow_times[-1]}
            if follow_times else None,
        'success_distance': {'p50': round(pct(accepted, .5), 1),
                             'p90': round(pct(accepted, .9), 1),
                             'max': round(accepted[-1], 1) if accepted else None},
        'accept_median': round(float(np.median([s['accept'] for s in successes])), 1)
            if successes else None,
        'failures_detail': failures,
        'saved_crops': saved,
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"süre {summary['seconds']} sn | seyahat {args.travel} sn | tik engelli {blocked} "
          f"| halkasız {no_ring_ticks}")
    print(f"bölüm {summary['episodes']} | başarılı {summary['successes']} | "
          f"başarısız {summary['failures']} | oran %{summary['failure_rate']*100:.1f}")
    print(f"başarıda kayma: p50 {summary['success_distance']['p50']} / "
          f"p90 {summary['success_distance']['p90']} / maks {summary['success_distance']['max']} "
          f"(kabul eşiği ort. {summary['accept_median']})")
    print('koruma anında:', guard_classes)
    print('takip sonucu:', follow_counts,
          '| yeniden görülme:', summary['follow_seconds'])
    print(f'kayıtlı kare: {saved} -> {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
