"""
Pulse analysis for a reed-contact anemometer on a Raspberry Pi GPIO.

Timing model
------------
All timestamps are integer microseconds on one monotonic time base
(`now_us()`), so the analysis is independent of where the edges come from:

  PigpioSource  – edges from the pigpio daemon (µs ticks, unwrapped and
                  shifted onto the monotonic base)
  SimSource     – synthetic edges for development without hardware

An edge with level 0 means "contact closed" (the pull-up is pulled to GND),
level 1 means "contact open".  A falling edge that arrives within
`debounce_ms` of the previous accepted falling edge is counted as bounce
(glitch) rather than as a pulse.
"""

import collections
import math
import random
import threading
import time


def now_us():
    return time.monotonic_ns() // 1000


class PulseAnalyzer:
    """Thread-safe edge collector + metric calculator."""

    def __init__(self, debounce_ms=5.0, timeout_s=3.0, window_s=5.0,
                 factor=1.44, unit="km/h", pulses_per_rev=1):
        self._lock = threading.Lock()
        self.debounce_us = int(debounce_ms * 1000)
        self.timeout_s = timeout_s
        self.window_s = window_s
        self.factor = factor
        self.unit = unit
        self.pulses_per_rev = max(1, pulses_per_rev)
        self.reset()

    # ── state ────────────────────────────────────────────────────────────────
    def reset(self):
        with self._lock:
            self.t_start = now_us()
            self.pulses = collections.deque(maxlen=20000)   # accepted falls (µs)
            self.glitches = collections.deque(maxlen=20000)  # rejected falls (µs)
            self.lows = collections.deque(maxlen=200)        # closure durations (µs)
            self.total_edges = 0
            self.total_pulses = 0
            self.total_glitches = 0
            self.t_accept = None        # last accepted falling edge
            self.t_last_rise = None     # last rising edge after t_accept
            self.low_pending = False
            self.level = None

    # ── input (called from the source thread) ────────────────────────────────
    def edge(self, t_us, level):
        with self._lock:
            self.total_edges += 1
            self.level = level
            if level == 0:
                if self.t_accept is None or (t_us - self.t_accept) >= self.debounce_us:
                    self._finalize_low()
                    self.pulses.append(t_us)
                    self.total_pulses += 1
                    self.t_accept = t_us
                    self.t_last_rise = None
                    self.low_pending = True
                else:
                    self.glitches.append(t_us)
                    self.total_glitches += 1
            else:
                self.t_last_rise = t_us

    def _finalize_low(self):
        """Closure duration = first accepted fall → last rise before next pulse."""
        if self.low_pending and self.t_last_rise is not None and self.t_accept is not None:
            d = self.t_last_rise - self.t_accept
            if d > 0:
                self.lows.append(d)
        self.low_pending = False

    # ── output ───────────────────────────────────────────────────────────────
    def snapshot(self, now=None):
        now = now_us() if now is None else now
        with self._lock:
            if (self.low_pending and self.t_last_rise is not None
                    and now - self.t_last_rise > self.debounce_us):
                self._finalize_low()

            uptime = (now - self.t_start) / 1e6
            last = self.pulses[-1] if self.pulses else None
            age = (now - last) / 1e6 if last is not None else None
            present = age is not None and age < self.timeout_s

            # pulses inside the frequency window
            win_us = int(self.window_s * 1e6)
            recent = []
            for t in reversed(self.pulses):
                if now - t > win_us:
                    break
                recent.append(t)
            recent.reverse()

            if not present:
                freq = 0.0
            elif len(recent) >= 2:
                span = (recent[-1] - recent[0]) / 1e6
                freq = (len(recent) - 1) / span if span > 0 else 0.0
            else:
                freq = len(recent) / self.window_s

            lows = list(self.lows)[-50:]
            if lows:
                low_min, low_avg, low_max = (min(lows) / 1000, sum(lows) / len(lows) / 1000,
                                             max(lows) / 1000)
            else:
                low_min = low_avg = low_max = None
            duty = (low_avg / 1000) * freq * 100 if (low_avg and freq > 0) else None

            # bounce ratio over the last 60 s
            cut = now - 60_000_000
            g60 = sum(1 for t in reversed(self.glitches) if t >= cut)
            p60 = sum(1 for t in reversed(self.pulses) if t >= cut)
            bounce = 100.0 * g60 / (g60 + p60) if (g60 + p60) else 0.0

            level = self.level

        if not lows:
            quality = ("none", "noch keine Pulse")
        elif bounce > 10 or (low_min is not None and low_min < 1.0):
            quality = ("serious", "starkes Prellen")
        elif bounce > 0:
            quality = ("warning", "leichtes Prellen")
        else:
            quality = ("good", "sauber")

        return {
            "present": present,
            "age_s": None if age is None else round(age, 1),
            "level": {0: "LOW", 1: "HIGH"}.get(level, "?"),
            "freq_hz": round(freq, 2),
            "pulses_per_min": round(freq * 60, 1),
            "rpm": round(freq * 60 / self.pulses_per_rev, 1),
            "wind": round(freq * self.factor, 1),
            "wind_unit": self.unit,
            "low_ms": {"min": _r(low_min), "avg": _r(low_avg), "max": _r(low_max)},
            "duty_pct": _r(duty),
            "bounce_pct": round(bounce, 1),
            "quality": {"level": quality[0], "text": quality[1]},
            "total_pulses": self.total_pulses,
            "total_glitches": self.total_glitches,
            "total_edges": self.total_edges,
            "uptime_s": round(uptime, 0),
            "config": {
                "debounce_ms": self.debounce_us / 1000,
                "timeout_s": self.timeout_s,
                "window_s": self.window_s,
                "factor": self.factor,
                "unit": self.unit,
                "pulses_per_rev": self.pulses_per_rev,
            },
        }


def _r(v, nd=1):
    return None if v is None else round(v, nd)


# ── Edge sources ─────────────────────────────────────────────────────────────

class PigpioSource:
    """Edges from the pigpio daemon.  Requires `sudo systemctl start pigpiod`."""

    def __init__(self, analyzer, gpio=17, pull_up=True):
        import pigpio
        self._pigpio = pigpio
        self.analyzer = analyzer
        self.gpio = gpio
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpiod läuft nicht – starten mit: sudo systemctl start pigpiod")
        self.pi.set_mode(gpio, pigpio.INPUT)
        self.pi.set_pull_up_down(gpio, pigpio.PUD_UP if pull_up else pigpio.PUD_OFF)
        # map 32-bit µs ticks (wrap every ~72 min) onto the monotonic base
        self._last_tick = self.pi.get_current_tick()
        self._wraps = 0
        self._offset = now_us() - self._last_tick
        self._cb = self.pi.callback(gpio, pigpio.EITHER_EDGE, self._on_edge)

    def _unwrap(self, tick):
        if tick < self._last_tick and (self._last_tick - tick) > (1 << 31):
            self._wraps += 1
        self._last_tick = tick
        return tick + (self._wraps << 32)

    def _on_edge(self, gpio, level, tick):
        if level == 2:                       # watchdog, not an edge
            return
        self.analyzer.edge(self._unwrap(tick) + self._offset, level)

    @property
    def contact_closed(self):
        return self.pi.read(self.gpio) == 0

    def describe(self):
        return f"pigpio GPIO {self.gpio} (Pull-up intern)"

    def close(self):
        try:
            self._cb.cancel()
        finally:
            self.pi.stop()


class SimSource(threading.Thread):
    """
    Synthetic anemometer for development: hand-turning ramp, a pause with no
    signal, then a fan-driven burst, repeated.  A few pulses bounce.
    """

    def __init__(self, analyzer):
        super().__init__(daemon=True, name="sim-source")
        self.analyzer = analyzer
        self.contact_closed = False
        self._stop = threading.Event()
        self.start()

    def describe(self):
        return "Simulation (keine Hardware)"

    def close(self):
        self._stop.set()

    def _pulse(self, low_s, bouncy=False):
        a = self.analyzer
        self.contact_closed = True
        a.edge(now_us(), 0)
        if bouncy:                               # 3 extra toggles within 2 ms
            for _ in range(3):
                time.sleep(0.0003); a.edge(now_us(), 1)
                time.sleep(0.0003); a.edge(now_us(), 0)
        time.sleep(low_s)
        self.contact_closed = False
        a.edge(now_us(), 1)

    def run(self):
        while not self._stop.is_set():
            t0 = time.monotonic()                      # phase 1: hand ramp 0.5 → 6 Hz
            while time.monotonic() - t0 < 25 and not self._stop.is_set():
                f = 0.5 + 5.5 * (time.monotonic() - t0) / 25
                period = 1.0 / f
                self._pulse(min(0.030, period * 0.3), bouncy=random.random() < 0.05)
                time.sleep(max(0.0, period - 0.030) * random.uniform(0.9, 1.1))
            if self._stop.wait(8):                     # phase 2: no signal
                break
            t0 = time.monotonic()                      # phase 3: fan ~12 Hz
            while time.monotonic() - t0 < 15 and not self._stop.is_set():
                f = 12 + 2 * math.sin(time.monotonic())
                self._pulse(0.008)
                time.sleep(max(0.0, 1.0 / f - 0.008))
            if self._stop.wait(4):
                break
