# Blue-wire protocol (PWM variant) — notes from one heater

Decoded from edge timings captured by the ESP32 itself (interrupt on both edges), November 2026.
Heater: VEVOR diesel air heater with the 5-button LCD controller (433 MHz icon), 3-wire cable (red 5 V, blue data, black GND).
The same controller is used on many other Chinese heaters.
Not verified with an oscilloscope.

## Not the Afterburner protocol

The well-known "blue wire" protocol supported by Afterburner is a UART at 25000 baud with 24-byte frames and CRC16.
This heater/controller pair uses a different, much slower PWM encoding (below). A UART receiver at 25000 baud on this
line receives only 0x00 bytes (tested). Both protocols use the same three-wire cable (red 5 V, blue data, black GND),
so the wire colour alone does not tell you which one you have.

## Physical layer

- Single wire, idle **high**, about **3.3 V** logic on this heater (multimeter shows 2.2–3.6 V while data flows).
- The ESP32 connects through a 1 kΩ series resistor; it drives the line as push-pull only while sending and
  releases it (input) right after.

## Bit and word format

- Bit period about **12 ms**: `0` = 4 ms high + 8 ms low, `1` = 8 ms high + 4 ms low (decode: high longer than low → 1).
- Every word starts with a **sync**: line low for **30 ms**.
- Frame once per second: **command word, 8 bits** (from the controller, MSB first) followed 1–2 ms later by the
  **reply word, 16 bits** from the heater.
- Before a controller command the line is high for ~650 ms; before the reply only ~1.5 ms.

## Commands (8 bit)

| Code | Meaning |
|---|---|
| `A6` | status / no key pressed (sent continuously) |
| `A2` | power: **toggles** start ↔ stop. Ignored during purge |
| `A3` | level up |
| `A4` | level down |
| `AF` | temperature request (reply `0x4xxx`) |
| `AB` | unknown (reply `0xA00C`) |

The controller sends a key code once (one frame), then returns to `A6`.

## Replies (16 bit)

`0x6xxx` — state and level. Low nibble = level − 1 (0..5) while running.

| Word (examples) | State |
|---|---|
| `600D` | stopped (idle) |
| `6042` → `6842` → `6942` | starting (first seconds … ~80 s) |
| `6D42`, `6C42` (`6C40`…`6C45`) | running (high byte `6C`/`6D`) |
| `61C0`, `64C0`, `6CC0`, `69C0` | purge / cooldown after stop (low byte `C0`) |

The state names "starting" vs "running" are inferred from timing, not from documentation.

`0x4xxx` — internal heater temperature, low 12 bits = **10-bit ADC reading of an NTC thermistor** (raw rises with temperature).
Fitted on 7 pairs "controller screen °F + raw" (error ≈ 2 °C):

```
T[K] = 4055.85 / ( ln(1023 / raw − 1) + 12.0813 )
```

| raw | °C | controller screen |
|---|---|---|
| 344 | 45 | 82–114 °F |
| 440 | 55 | 129 °F |
| 681 | 83 | 183 °F |
| 883 | 123 | 255 °F |
| 992 | 198 | 388 °F |

The controller screen caps at 399 °F. The controller shows the temperature only while the heater runs
(not during purge), and the heater answers `AF` only then.

## Sharing the line with the controller

The ESP32 sends its own command frame only in the pause between controller frames: **80–300 ms after the last edge**
(the controller is silent ~650 ms after the heater's reply; our frame + reply takes ~370 ms). Frame shape:
high 20 ms, low 30 ms, 8 bits, high 1.5 ms, release. Commands are verified by the next replies and retried up to 3 times.
With the controller disconnected the ESP32 polls with `A6` once per second itself.
A few percent of frames get lost, so never assume a command arrived without checking the reply.
