#!/usr/bin/env python3
"""Reference encoder/decoder for the PWM "blue wire" protocol of the 5-button LCD diesel heater controller.

No Home Assistant, no ESPHome, no dependencies: plain Python 3.8+. Use it to
  * decode a logic-analyzer capture of the blue wire (CSV: time, level),
  * check your own decoder against known frames,
  * see exactly which edges a command frame consists of before you write a transmitter.

Protocol summary (details: docs/protocol.md):
  * one wire, idle HIGH; a word starts with a SYNC = line LOW for 30 ms;
  * a bit is HIGH then LOW, about 12 ms together: "0" = 4 ms high + 8 ms low, "1" = 8 ms high + 4 ms low, MSB first;
  * a frame = command word (8 bit, from the controller) + reply word (16 bit, from the heater) 1-2 ms later;
  * commands: A6 status, A2 power toggle, A3 level up, A4 level down, AF temperature request.

Usage:
  python bluewire.py --selftest            encode a few frames, add jitter, decode them again
  python bluewire.py --demo                print the edge list of one command frame and a decoded example
  python bluewire.py capture.csv           decode a capture (time in seconds, level 0/1; header lines are skipped)
  python bluewire.py capture.csv --us      the same, time column in microseconds
  python bluewire.py capture.csv --column 2   level is in CSV column 2 (0 = first column, default 1)
  python bluewire.py capture.csv --all     print every word, not only the changes
"""
import csv
import math
import random
import sys
from typing import Iterable, Iterator, List, NamedTuple, Optional, Tuple

# ---- timing, microseconds -------------------------------------------------------------------------------------------
SYNC_US = 30000          # sync: low level before every word
SYNC_MIN_US = 20000      # a low level at least this long is treated as a sync
BIT_LONG_US = 8000       # "1": high 8 ms + low 4 ms;  "0": high 4 ms + low 8 ms
BIT_SHORT_US = 4000
GLITCH_US = 1500         # a high or low level shorter than this inside a word marks the word as bad
WORD_END_HIGH_US = 15000  # inside a word the line is never high longer than 8 ms: a longer high level ends the word
REPLY_GAP_US = 1500      # the heater starts its reply 1-2 ms after the command word

COMMANDS = {
    0xA6: "status (no key pressed)",
    0xA2: "power: TOGGLES start/stop (ignored during purge)",
    0xA3: "level up",
    0xA4: "level down",
    0xAF: "temperature request",
    0xAB: "unknown (reply 0xA00C)",
}

Edge = Tuple[int, int]   # (time in microseconds, line level AFTER the edge: 0 or 1)


class Word(NamedTuple):
    start_us: int        # time of the falling edge that starts the sync
    bits: int            # number of bits received
    value: int
    ok: bool             # False: a glitch was seen inside the word


# ---- decoder --------------------------------------------------------------------------------------------------------
def decode_edges(edges: Iterable[Edge]) -> Iterator[Word]:
    """Turn a stream of edges into words. Feed it every level change of the blue wire."""
    prev_t: Optional[int] = None
    prev_level = 1
    high_us = 0
    in_word = False
    bad = False
    nbits = value = start = 0
    sync_start = 0
    for t, level in edges:
        if prev_t is None:
            prev_t, prev_level = t, level
            continue
        if level == prev_level:          # two edges to the same level: a glitch was missed
            bad = True
            continue
        d = t - prev_t
        if prev_level == 1:              # a HIGH level just ended (falling edge)
            if in_word and nbits and d > WORD_END_HIGH_US:
                yield Word(start, nbits, value, not bad)
                in_word = False
            high_us = d
            sync_start = t
        else:                            # a LOW level just ended (rising edge)
            if d >= SYNC_MIN_US:         # sync: the previous word (if any) is complete, a new one starts
                if in_word and nbits:
                    yield Word(start, nbits, value, not bad)
                in_word, bad, nbits, value, start = True, False, 0, 0, sync_start
            elif in_word:
                if high_us < GLITCH_US or d < GLITCH_US:
                    bad = True
                value = (value << 1) | (1 if high_us > d else 0)   # compare high with low: robust to clock drift
                nbits += 1
        prev_t, prev_level = t, level
    if in_word and nbits:
        yield Word(start, nbits, value, not bad)


# ---- encoder --------------------------------------------------------------------------------------------------------
def encode_word(value: int, bits: int, t0: int) -> Tuple[List[Edge], int]:
    """Edges of one word whose sync starts at t0 (the line is HIGH before). Returns (edges, time of the last edge)."""
    edges: List[Edge] = [(t0, 0)]
    t = t0 + SYNC_US
    edges.append((t, 1))
    for i in range(bits - 1, -1, -1):
        one = (value >> i) & 1
        t += BIT_LONG_US if one else BIT_SHORT_US
        edges.append((t, 0))
        t += BIT_SHORT_US if one else BIT_LONG_US
        edges.append((t, 1))
    return edges, t


def encode_frame(command: int, reply: Optional[int], t0: int) -> Tuple[List[Edge], int]:
    """A command word and (optionally) the heater's 16-bit reply 1.5 ms later."""
    edges, t = encode_word(command, 8, t0)
    if reply is not None:
        more, t = encode_word(reply, 16, t + REPLY_GAP_US)
        edges += more
    return edges, t


def transmit_plan(command: int) -> List[Tuple[int, int]]:
    """What a transmitter has to do to send one command: a list of (level, hold time in microseconds).

    Drive the line for the listed times, then release it (switch the pin back to input): the heater answers 1-2 ms later.
    With the original controller connected, start only in the pause between its frames, 80-250 ms after the last edge.
    """
    plan = [(1, 20000), (0, SYNC_US)]
    for i in range(7, -1, -1):
        one = (command >> i) & 1
        plan.append((1, BIT_LONG_US if one else BIT_SHORT_US))
        plan.append((0, BIT_SHORT_US if one else BIT_LONG_US))
    plan.append((1, 1500))
    return plan


# ---- meaning of the 16-bit reply ------------------------------------------------------------------------------------
def raw_to_celsius(raw: int) -> Optional[float]:
    """Internal heater temperature: raw = 10-bit ADC reading of an NTC thermistor (fitted on 7 points, error about 2 C)."""
    if not 0 < raw < 1023:
        return None
    return 4055.85 / (math.log(1023.0 / raw - 1.0) + 12.0813) - 273.15


def parse_reply(word: int) -> dict:
    """Interpret a 16-bit heater reply. State names "starting"/"running" are inferred from timing, not from documentation."""
    top = word >> 12
    if top == 0x4:
        raw = word & 0x0FFF
        return {"kind": "temperature", "raw": raw, "celsius": raw_to_celsius(raw)}
    if top != 0x6:
        return {"kind": "unknown"}
    high, low = word >> 8, word & 0xFF
    level = None
    if low in (0x0D, 0x0C):              # 0x600C shows up for single frames instead of 0x600D while idle
        state = "stopped"
    elif low & 0xC0 == 0xC0:
        state = "purge"
    elif low & 0xC0 == 0x40:
        state = "running" if high in (0x6C, 0x6D) else "starting"
        if low & 0x0F <= 5:
            level = (low & 0x0F) + 1     # power level 1..6
    else:
        state = "unknown"
    return {"kind": "state", "state": state, "level": level}


def describe(word: Word) -> str:
    if not word.ok:
        return f"bad word ({word.bits} bits, 0x{word.value:X})"
    if word.bits == 8:
        return f"command 0x{word.value:02X}  {COMMANDS.get(word.value, 'unknown command')}"
    if word.bits == 16:
        info = parse_reply(word.value)
        if info["kind"] == "temperature":
            c = info["celsius"]
            return f"reply   0x{word.value:04X}  temperature raw {info['raw']}" + (f" = {c:.0f} C" if c is not None else "")
        if info["kind"] == "state":
            lvl = f", level {info['level']}" if info["level"] else ""
            return f"reply   0x{word.value:04X}  {info['state']}{lvl}"
        return f"reply   0x{word.value:04X}  unknown"
    return f"word of {word.bits} bits: 0x{word.value:X}"


# ---- capture files --------------------------------------------------------------------------------------------------
def read_capture(path: str, time_in_us: bool = False, column: int = 1) -> List[Edge]:
    """CSV with a time column (first) and a level column. Rows may be samples or only transitions; header lines are skipped."""
    edges: List[Edge] = []
    last = None
    with open(path, newline="") as f:
        for row in csv.reader(f):
            try:
                t = float(row[0])
                level = 1 if float(row[column]) >= 0.5 else 0
            except (ValueError, IndexError):
                continue
            if level != last:
                edges.append((int(round(t if time_in_us else t * 1e6)), level))
                last = level
    return edges


# ---- self-test and demo ---------------------------------------------------------------------------------------------
def selftest() -> int:
    rnd = random.Random(1)
    frames = [(0xA6, 0x600D), (0xA2, 0x6042), (0xA6, 0x6842), (0xA3, 0x6C43), (0xA4, 0x6C42), (0xAF, 0x42A9),
              (0xA2, 0x64C0), (0xA6, 0x69C0), (0xA6, 0x600C), (0xAB, 0xA00C), (0xA6, None)]
    edges: List[Edge] = [(0, 1)]
    t = 500000
    for cmd, reply in frames:
        more, end = encode_frame(cmd, reply, t)
        edges += more
        t = end + 650000
    jittered = [(te + rnd.randint(-600, 600), lv) for te, lv in edges]   # 0.6 ms of jitter on every edge
    expected_all = []
    for cmd, reply in frames:
        expected_all.append((8, cmd))
        if reply is not None:
            expected_all.append((16, reply))
    failures = 0
    for name, data in (("clean", edges), ("jitter 0.6 ms", jittered)):
        got = [(w.bits, w.value) for w in decode_edges(data) if w.ok]
        ok = got == expected_all
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  decode, {name}: {len(got)} words")
    checks = [
        (parse_reply(0x600D)["state"] == "stopped", "600D = stopped"),
        (parse_reply(0x6042) == {"kind": "state", "state": "starting", "level": 3}, "6042 = starting, level 3"),
        (parse_reply(0x6C45) == {"kind": "state", "state": "running", "level": 6}, "6C45 = running, level 6"),
        (parse_reply(0x69C0)["state"] == "purge", "69C0 = purge"),
        (abs(raw_to_celsius(681) - 83) < 1.5, "raw 681 is about 83 C"),
        (abs(raw_to_celsius(440) - 55) < 1.5, "raw 440 is about 55 C"),
        (sum(us for _, us in transmit_plan(0xA2)) == 20000 + 30000 + 8 * 12000 + 1500, "command frame lasts 147.5 ms"),
    ]
    glitch = list(edges[:6]) + [(edges[5][0] + 200, 0), (edges[5][0] + 400, 1)] + list(edges[6:])
    first = next(decode_edges(sorted(glitch)))
    checks.append((not first.ok, "a 0.2 ms glitch marks the word as bad"))
    for ok, name in checks:
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return failures


def demo() -> None:
    print("Sending command 0xA2 (power toggle): drive the line like this, then release it")
    for level, us in transmit_plan(0xA2):
        print(f"  {'HIGH' if level else 'LOW '} {us / 1000:5.1f} ms")
    print("\nA decoded frame (command from the controller + reply from the heater):")
    edges, _ = encode_frame(0xA6, 0x6C42, 1000000)
    for w in decode_edges([(0, 1)] + edges):
        print(f"  {w.start_us / 1e6:9.3f} s  {describe(w)}")


def main(argv: List[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--demo" in argv or len(argv) < 2:
        if len(argv) < 2:
            print(__doc__)
        demo()
        return 0
    column = 1
    if "--column" in argv:
        column = int(argv[argv.index("--column") + 1])
    path = next(a for a in argv[1:] if a.lower().endswith((".csv", ".txt")) or not (a.startswith("--") or a.isdigit()))
    edges = read_capture(path, "--us" in argv, column)
    print(f"{len(edges)} edges")
    last = {}                            # last printed word per word length: repeats are printed only with --all
    n_ok = n_bad = 0
    for w in decode_edges(edges):
        n_ok += w.ok
        n_bad += not w.ok
        if "--all" in argv or not w.ok or last.get(w.bits) != w.value:
            print(f"{w.start_us / 1e6:10.3f} s  {describe(w)}")
        if w.ok:
            last[w.bits] = w.value
    print(f"words: {n_ok} ok, {n_bad} bad (repeated words are hidden, use --all to see every word)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
