# Generator of docs/protocol-timing.svg: one frame of the blue-wire protocol (command A6 + reply 0x600D) and the bit encoding.
import os
W, H = 1400, 620
o = []
A = o.append
def text(x, y, s, size=13, anchor="start", weight="normal", fill="#263238"):
    A(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{s}</text>')
def wave(x0, y_hi, y_lo, segs, px, color):
    # segs: list of (level, duration_ms)
    pts = []; x = x0
    for lvl, d in segs:
        y = y_hi if lvl else y_lo
        pts.append((x, y)); x += d * px; pts.append((x, y))
    A('<polyline points="' + " ".join(f"{a:.1f},{b}" for a, b in pts) + f'" fill="none" stroke="{color}" stroke-width="2.5"/>')
    return x
def bits(code, n):
    return [((code >> (n - 1 - i)) & 1) for i in range(n)]
def word(code, n):
    segs = [(0, 30)]
    for b in bits(code, n):
        segs += [(1, 8 if b else 4), (0, 4 if b else 8)]
    return segs

A(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="#fafaf7"/>')
text(40, 42, "Blue-wire protocol: one frame (controller command A6 + heater reply 0x600D)", 22, weight="bold")
text(40, 66, "Idle line is high (~3.3 V). Bit period ~12 ms. Every word starts with a 30 ms low sync. One frame per second.", 14, fill="#546e7a")

# --- frame ---
px = 3.4; x0 = 40; yh, yl = 130, 190
segs = [(1, 20)] + word(0xA6, 8) + [(1, 1.5)] + word(0x600D, 16) + [(1, 20)]
wave(x0, yh, yl, segs, px, "#1565c0")
# annotations
x = x0 + 20 * px
A(f'<rect x="{x:.1f}" y="200" width="{30*px:.1f}" height="22" fill="#eceff1"/>'); text(x + 15 * px, 216, "sync 30 ms", 12, anchor="middle")
cmd_start = x + 30 * px; cmd_len = 8 * 12 * px
A(f'<rect x="{cmd_start:.1f}" y="200" width="{cmd_len:.1f}" height="22" fill="#e3f2fd"/>'); text(cmd_start + cmd_len / 2, 216, "command 8 bit: A6 = 1010 0110", 12, anchor="middle")
text(cmd_start + cmd_len / 2, 112, "from the controller (master)", 12, anchor="middle", fill="#546e7a")
x = cmd_start + cmd_len + 1.5 * px
A(f'<rect x="{x:.1f}" y="200" width="{30*px:.1f}" height="22" fill="#eceff1"/>'); text(x + 15 * px, 216, "sync", 12, anchor="middle")
rs = x + 30 * px; rl = 16 * 12 * px
A(f'<rect x="{rs:.1f}" y="200" width="{rl:.1f}" height="22" fill="#e8f5e9"/>'); text(rs + rl / 2, 216, "reply 16 bit: 0x600D = 0110 0000 0000 1101 (stopped)", 12, anchor="middle")
text(rs + rl / 2, 112, "from the heater, 1–2 ms after the command", 12, anchor="middle", fill="#546e7a")
# bit labels
x = cmd_start
for b in bits(0xA6, 8):
    text(x + 6 * px, 156, str(b), 12, anchor="middle", fill="#1565c0"); x += 12 * px
x = rs
for b in bits(0x600D, 16):
    text(x + 6 * px, 156, str(b), 12, anchor="middle", fill="#1565c0"); x += 12 * px
text(40, 250, "then ~650 ms idle high until the next frame (the ESP32 sends its own frame in this pause, 80–300 ms after the last edge)", 13, fill="#546e7a")

# --- bit encoding ---
text(40, 300, "Bit encoding", 18, weight="bold")
px2 = 9; yh2, yl2 = 340, 390
x = wave(60, yh2, yl2, [(0, 3), (1, 4), (0, 8), (1, 1)], px2, "#1565c0")
text(60 + 3 * px2 + 2 * px2, 332, "4 ms", 12, anchor="middle"); text(60 + 7 * px2 + 4 * px2, 405, "8 ms", 12, anchor="middle")
text(60 + 7 * px2, 425, "\"0\" = 4 ms high + 8 ms low", 13, anchor="middle", weight="bold")
x = wave(420, yh2, yl2, [(0, 3), (1, 8), (0, 4), (1, 1)], px2, "#1565c0")
text(420 + 3 * px2 + 4 * px2, 332, "8 ms", 12, anchor="middle"); text(420 + 11 * px2 + 2 * px2, 405, "4 ms", 12, anchor="middle")
text(420 + 7 * px2, 425, "\"1\" = 8 ms high + 4 ms low", 13, anchor="middle", weight="bold")
text(800, 345, "Decode: high longer than low → 1.", 13)
text(800, 367, "Low ≥ 20 ms → sync (start of a word).", 13)
text(800, 389, "Line high > 15 ms after bits → word finished.", 13)
text(800, 411, "MSB first.", 13)

# --- tables ---
text(40, 470, "Commands (8 bit)", 16, weight="bold")
for i, (c, m) in enumerate([("A6", "status, no key"), ("A2", "power: toggles start/stop"), ("A3", "level up"), ("A4", "level down"), ("AF", "temperature request")]):
    text(40, 495 + i * 22, c, 13, weight="bold"); text(90, 495 + i * 22, m, 13)
text(480, 470, "Replies (16 bit)", 16, weight="bold")
for i, (c, m) in enumerate([("600D", "stopped"), ("6042 / 6842 / 6942", "starting (level = low nibble + 1)"), ("6C4x / 6D4x", "running, level x+1"), ("xxC0 (61C0, 64C0, 69C0)", "purge after stop"), ("4xxx", "temperature: 10-bit NTC ADC (see protocol.md)")]):
    text(480, 495 + i * 22, c, 13, weight="bold"); text(700, 495 + i * 22, m, 13)
A('</svg>')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "protocol-timing.svg")
open(out, "w", encoding="utf-8").write("\n".join(o))
print(out)
