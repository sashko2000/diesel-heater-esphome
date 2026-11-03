# Generator of the wiring diagram (controller + ESP32 + power) diesel-heater-wiring.svg: python3 diesel-heater-wiring_gen.py (writes the SVG next to the script)
import os
W, H = 1400, 1130
o = []
A = o.append

BLK="#212121"; BLU="#1565c0"; V5="#d84315"

def line(pts, c, w=2.5, dash=None):
    d = " ".join(f"{x},{y}" for x, y in pts)
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<polyline points="{d}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"{ds}/>')
def dot(x, y, c, r=4.5):
    A(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>')
def pin(x, y, c):
    A(f'<circle cx="{x}" cy="{y}" r="5" fill="#fff" stroke="{c}" stroke-width="2"/>')
def text(x, y, s, size=13, anchor="start", weight="normal", fill="#263238"):
    A(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{s}</text>')
def box(x, y, w, h, fill, stroke, r=10, dash=None):
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"{ds}/>')
def resistor_h(x, y, w, label):
    A(f'<rect x="{x}" y="{y-12}" width="{w}" height="24" rx="3" fill="#fff" stroke="{BLK}" stroke-width="2"/>')
    text(x + w/2, y - 20, label, 13, anchor="middle", weight="bold")
def resistor_v(cx, y, h, label):
    A(f'<rect x="{cx-12}" y="{y}" width="24" height="{h}" rx="3" fill="#fff" stroke="{BLK}" stroke-width="2"/>')
    text(cx + 22, y + h/2 + 4, label, 13, weight="bold")
def gnd_symbol(x, y):
    line([(x-14, y), (x+14, y)], BLK, 2.5)
    line([(x-9, y+6), (x+9, y+6)], BLK, 2.5)
    line([(x-4, y+12), (x+4, y+12)], BLK, 2.5)

A(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="DejaVu Sans, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="#fafaf7"/>')
text(40, 45, "Diesel Heater — wiring: controller, ESP32 and power", 26, weight="bold")
text(40, 70, "Works together with the controller: ESP32 on the blue wire through 1 kOhm. Power: USB, or permanently 12 V through a fuse and a Mini360 (dashed, recommended).", 14, fill="#546e7a")

C12 = "#b71c1c"
# legend
lx = 40
for c, lab in [(BLU, "signal (blue wire, GPIO16: receive and transmit)"), (BLK, "common ground (GND)"), (C12, "+12 V"), (V5, "5 V / controller red wire")]:
    line([(lx, 102), (lx+30, 102)], c, 4)
    text(lx+38, 106, lab, 13)
    lx += 38 + len(lab)*7.4 + 26

# ---------- controller ----------
box(60, 140, 260, 250, "#eceff1", "#455a64")
text(80, 168, "Heater controller", 16, weight="bold")
text(80, 188, "controller cable goes to the heater,", 12, fill="#546e7a")
text(80, 206, "3 wires (controller stays connected)", 12, fill="#546e7a")
for y, lab, c in [(240, "red: 5 V (4.96 V)", V5), (290, "blue: data (2.3–3.4 V)", BLU), (350, "black: GND", BLK)]:
    text(308, y + 4, lab, 13, anchor="end")
    pin(320, y, c)
line([(320, 240), (400, 240)], V5, 2.5, dash="6 5")
text(412, 245, "×", 22, weight="bold", fill=V5)
text(440, 245, "do not connect the red wire to the ESP32 (the controller cannot supply it)", 12, fill=V5)

# blue: R1 -> GPIO16
line([(320, 290), (520, 290)], BLU, 2.5)
resistor_h(520, 290, 100, "R1 1 kOhm")
line([(620, 290), (900, 290)], BLU, 2.5)
text(760, 282, "to GPIO16", 11, anchor="middle", fill="#546e7a")
text(420, 326, "R1 1 kOhm: protects the pin and lets the ESP32 drive the line", 11, fill="#546e7a")
text(420, 342, "(collision current at most 3 mA). No divider to GND.", 11, fill="#546e7a")

# ---------- ESP32 ----------
box(900, 140, 340, 330, "#eceff1", "#455a64")
text(920, 170, "ESP32 DevKit (heater)", 16, weight="bold")
text(920, 190, "power: USB (5 V)", 12, fill="#546e7a")
text(920, 208, "permanent: VIN from Mini360 (no USB)", 12, fill="#546e7a")
for y, lab, c in [(290, "GPIO16 · receive and transmit", BLU), (350, "GND", BLK), (420, "VIN (5 V)", V5)]:
    pin(900, y, c)
    text(918, y + 4, lab, 13)

# common ground (GND bus)
line([(320, 350), (900, 350)], BLK, 2.5)
dot(600, 350, BLK)
line([(600, 350), (600, 380)], BLK, 2.5)
gnd_symbol(600, 380)
text(626, 400, "common ground", 11, fill="#546e7a")

# ---------- power 12 V -> Mini360 -> VIN (dashed) ----------
text(40, 470, "ESP32 POWER FROM 12 V (dashed: instead of USB)", 16, weight="bold")
box(60, 490, 220, 150, "#eceff1", "#455a64", dash="8 5")
text(80, 518, "12 V supply", 16, weight="bold")
text(80, 538, "(battery terminal block)", 12, fill="#546e7a")
text(268, 574, "+12 V", 13, anchor="end"); text(268, 626, "minus", 13, anchor="end")
pin(280, 580, C12); pin(280, 620, BLK)
line([(280, 580), (360, 580)], C12, 3, dash="8 5")
A('<rect x="360" y="566" width="80" height="28" rx="4" fill="#fff8e1" stroke="#455a64" stroke-width="2"/>')
line([(368, 580), (432, 580)], BLK, 1.5)
text(400, 556, "F1 2 A", 14, anchor="middle", weight="bold")
text(400, 650, "in the +12 V line, close", 11, anchor="middle", fill="#546e7a")
text(400, 664, "to the source", 11, anchor="middle", fill="#546e7a")
line([(440, 580), (520, 580)], C12, 3, dash="8 5")
line([(280, 620), (520, 620)], BLK, 3, dash="8 5")
box(520, 490, 240, 150, "#e8f5e9", "#2e7d32", dash="8 5")
text(540, 518, "Mini360 (DC-DC 12→5 V)", 15, weight="bold")
text(540, 538, "input 12 V, output 5.0 V", 12, fill="#546e7a")
text(540, 632, "common minus", 11, fill="#546e7a")
pin(520, 580, C12); pin(520, 620, BLK); pin(760, 580, V5); pin(760, 620, BLK)
text(534, 584, "IN+", 12); text(534, 624, "IN−", 12)
text(746, 584, "OUT+", 12, anchor="end"); text(746, 624, "OUT−", 12, anchor="end")
# OUT+ -> VIN
line([(760, 580), (860, 580), (860, 420), (900, 420)], V5, 3, dash="8 5")
text(868, 520, "5.0 V", 13, weight="bold", fill=V5)
# OUT- -> GND bus
line([(760, 620), (800, 620), (800, 350)], BLK, 3, dash="8 5")
dot(800, 350, BLK)

# ---------- notes ----------
notes = [
    "1. Measured with the controller connected: red–black 4.96 V; blue–black 2.3–3.4 V (the meter averages the digital signal). The blue line is about 3.3 V logic: no divider needed (a 100 kOhm + 200 kOhm divider gave 1.3–2.3 V, below the ESP32 input threshold of about 2.5 V). Not verified with an oscilloscope.",
    "2. R1 is 1 kOhm so the ESP32 can drive the line (commands from HA). If the controller screen behaves strangely, use 5.1 kOhm: receiving still works, but commands from HA will not get through.",
    "3. Do NOT connect the controller red wire (5 V) to the ESP32: powering an ESP32 with Wi-Fi from it made the controller screen flicker (not enough current). With USB power the flicker was gone.",
    "4. Power: USB (5 V), or permanently (dashed): +12 V -> fuse F1 2 A (in the plus line, close to the source) -> Mini360 -> ESP32 VIN. Never connect USB and VIN at the same time.",
    "5. Before connecting the ESP32, feed the Mini360 with 12 V without load and set the output to 5.0 V with the trimmer and a multimeter (from the factory it is often set differently). Wires at least 0.5 mm². The board draws about 0.25 A at 5 V (about 0.12 A at 12 V), so the fuse has a large margin.",
    "6. Common ground is required: controller black wire, ESP32 GND, Mini360 output and 12 V minus are connected together.",
    "7. Protocol (see docs/protocol.md): not UART. PWM words: bit about 12 ms (\"0\" = 4 ms high + 8 ms low, \"1\" = the opposite), sync: low 30 ms. Frame: controller command 8 bit (A6 none, A2 power, A3 up, A4 down, AF temperature) + heater reply 16 bit. The board sends only the needed command in the pause between controller frames (80–300 ms after the last edge); verified: the controller kept working and the level changed by ESP32 commands. A2 toggles start/stop; a start during purge is impossible (neither from the controller nor from HA).",
    "8. This diagram is for working together with the controller. Without the controller the firmware also works (it polls A6 once per second itself).",
]
import textwrap
yy = 700
for n in notes:
    for k, part in enumerate(textwrap.wrap(n, width=150, subsequent_indent="    ")):
        text(40, yy, part, 13, fill="#37474f"); yy += 20
    yy += 8

A('</svg>')
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diesel-heater-wiring.svg")
open(out, "w", encoding="utf-8").write("\n".join(o))
print(out)
