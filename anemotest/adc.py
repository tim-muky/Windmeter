"""
Signal-level ("Signalstärke") measurement with an ADC.

The Pi cannot measure voltage itself, so an MCP3008 (SPI) samples the sensor
node continuously.  Idle the node sits at the pull-up voltage (≈ 3.3 V); while
the reed contact is closed it drops to

        V_low = V_idle · R_contact / (R_contact + R_pullup)

so from V_low and the known pull-up the contact resistance follows.  The
grade thresholds assume 3.3 V CMOS logic at the receiving end (PiLogger or
Pi): LOW must be < 0.8 V, better < 0.4 V.
"""

import collections
import random
import threading
import time


class Mcp3008Reader:
    """MCP3008 on SPI0 (CE0): CLK=GPIO11, MISO=GPIO9, MOSI=GPIO10, CS=GPIO8."""

    def __init__(self, bus=0, device=0, channel=0, vref=3.3, speed_hz=1_350_000):
        import spidev
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = speed_hz
        self.channel = channel
        self.vref = vref
        self._cmd = [1, (8 + channel) << 4, 0]

    def read(self):
        r = self.spi.xfer2(list(self._cmd))
        raw = ((r[1] & 3) << 8) | r[2]
        return raw * self.vref / 1023.0

    def describe(self):
        return f"MCP3008 Kanal {self.channel}, Vref {self.vref:g} V"

    def close(self):
        self.spi.close()


class SimAdcReader:
    """Synthetic ADC tied to a SimSource's contact state."""

    def __init__(self, source, vref=3.3, v_low=0.18, rate_hz=2000):
        self.source = source
        self.vref = vref
        self.v_low = v_low
        self._dt = 1.0 / rate_hz

    def read(self):
        time.sleep(self._dt)
        base = self.v_low if self.source.contact_closed else self.vref - 0.03
        return base + random.gauss(0, 0.008)

    def describe(self):
        return "Simulation"

    def close(self):
        pass


class AdcMonitor(threading.Thread):
    """Continuously samples the reader and derives idle / low levels."""

    def __init__(self, reader, pullup_ohm=10_000.0, vref=3.3):
        super().__init__(daemon=True, name="adc-monitor")
        self.reader = reader
        self.pullup_ohm = pullup_ohm
        self.vref = vref
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.error = None
        self.reset()
        self.start()

    def reset(self):
        with self._lock:
            self.v_now = None
            self.samples_per_s = 0.0
            self._bucket_max = 0.0            # max within the current 100 ms bucket
            self._bucket_t = time.monotonic()
            self._maxima = collections.deque(maxlen=100)   # 100 × 100 ms = 10 s
            self.in_closure = False
            self._closure_min = None
            self.lows = collections.deque(maxlen=50)
            self.closures = 0
            self._n = 0
            self._t_rate = time.monotonic()

    def close(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                v = self.reader.read()
            except Exception as exc:            # SPI error → report, keep trying
                self.error = str(exc)
                time.sleep(0.5)
                continue
            self.error = None
            self._ingest(v)

    def _idle_estimate(self):
        m = max(self._maxima) if self._maxima else self._bucket_max
        return m if m >= 1.0 else self.vref

    def _ingest(self, v):
        with self._lock:
            self.v_now = v
            self._n += 1
            t = time.monotonic()
            if t - self._t_rate >= 1.0:
                self.samples_per_s = self._n / (t - self._t_rate)
                self._n = 0
                self._t_rate = t
            if t - self._bucket_t >= 0.1:
                self._maxima.append(self._bucket_max)
                self._bucket_max = v
                self._bucket_t = t
            elif v > self._bucket_max:
                self._bucket_max = v

            idle = self._idle_estimate()
            if not self.in_closure:
                if v < 0.5 * idle:
                    self.in_closure = True
                    self._closure_min = v
            else:
                if v < self._closure_min:
                    self._closure_min = v
                if v > 0.75 * idle:
                    self.in_closure = False
                    self.lows.append(self._closure_min)
                    self.closures += 1

    def snapshot(self):
        with self._lock:
            v_now = self.v_now
            idle = self._idle_estimate()
            lows = list(self.lows)
            rate = self.samples_per_s
            closures = self.closures
            in_closure = self.in_closure
            err = self.error

        v_last = lows[-1] if lows else None
        v_avg = sum(lows) / len(lows) if lows else None
        v_worst = max(lows) if lows else None
        if v_avg is not None and idle - v_avg > 0.05:
            r_contact = v_avg * self.pullup_ohm / (idle - v_avg)
        else:
            r_contact = None

        if err:
            grade = ("critical", "ADC-Fehler: " + err)
        elif not lows:
            grade = ("none", "noch keine Schließung gemessen")
        elif v_worst <= 0.4:
            grade = ("good", "stark – LOW deutlich unter 0,4 V")
        elif v_worst <= 0.8:
            grade = ("warning", "ausreichend – LOW unter 0,8 V, aber wenig Reserve")
        elif v_worst <= 1.5:
            grade = ("serious", "schwach – LOW über 0,8 V, Übergangswiderstand zu hoch")
        else:
            grade = ("critical", "zu schwach – wird als Puls nicht sicher erkannt")
        idle_note = None
        if idle < 2.5:
            idle_note = "Ruhepegel niedrig: Leckstrom oder Teil-Kurzschluss?"

        return {
            "available": True,
            "reader": self.reader.describe(),
            "samples_per_s": round(rate),
            "v_now": _r3(v_now),
            "v_idle": _r3(idle),
            "v_low_last": _r3(v_last),
            "v_low_avg": _r3(v_avg),
            "v_low_worst": _r3(v_worst),
            "r_contact_ohm": None if r_contact is None else round(r_contact),
            "closures": closures,
            "in_closure": in_closure,
            "pullup_ohm": self.pullup_ohm,
            "grade": {"level": grade[0], "text": grade[1]},
            "idle_note": idle_note,
        }


def _r3(v):
    return None if v is None else round(v, 3)
