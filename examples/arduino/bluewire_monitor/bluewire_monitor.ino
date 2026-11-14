// Blue-wire monitor: a minimal Arduino sketch (ESP32) for the PWM "blue wire" protocol of the 5-button LCD
// diesel heater controller. No Home Assistant, no ESPHome. It prints every change on the line to the serial
// monitor and can send single commands. Use it as a starting point for your own controller.
//
// Wiring (see docs/diesel-heater-wiring.png): controller blue wire -> 1 kOhm resistor -> GPIO16, controller black -> GND.
// Do NOT connect the controller's red wire. The original controller stays connected.
//
// Serial monitor, 115200 baud. Type one character and press Enter:
//   t = request the temperature (0xAF)   + = level up (0xA3)   - = level down (0xA4)
//   P = power: TOGGLES start/stop (0xA2), capital letter on purpose. A diesel heater burns fuel: know what you start.
//   s = status request (0xA6), only useful when no controller is connected
//
// Protocol (details: docs/protocol.md): the line idles HIGH. A word starts with a sync = LOW for 30 ms. A bit is
// HIGH then LOW, about 12 ms together: "0" = 4 ms high + 8 ms low, "1" = 8 ms high + 4 ms low, MSB first. Once per
// second the controller sends an 8-bit command and the heater answers with a 16-bit word 1-2 ms later.
//
// What this sketch does NOT do (the ESPHome firmware in esphome/diesel-heater.yaml does): it does not check that a
// command was accepted and does not retry. A few percent of frames get lost, so always look at the reply.
//
// Status: the decoder and the transmit timing are the same as in the ESPHome firmware and were tested on a
// computer against a model of the line; this sketch itself has not been run on a board yet.

#include <Arduino.h>
#include <math.h>

const int PIN = 16;

// ---- edge capture (interrupt) ---------------------------------------------------------------------------------
const uint32_t RING = 256;
volatile uint32_t edgeTime[RING];
volatile uint8_t edgeLevel[RING];
volatile uint32_t head = 0;
volatile uint32_t lastEdgeUs = 0;
volatile bool sending = false;

void IRAM_ATTR onEdge() {
  if (sending) return;                       // our own edges are not decoded
  uint32_t now = micros();
  uint32_t h = head;
  edgeTime[h % RING] = now;
  edgeLevel[h % RING] = (uint8_t) digitalRead(PIN);
  lastEdgeUs = now;
  head = h + 1;
}

// ---- decoder state --------------------------------------------------------------------------------------------
uint32_t tail = 0;
bool havePrev = false, inWord = false, bad = false;
uint8_t prevLevel = 1;
uint32_t prevTime = 0, highUs = 0, nbits = 0, value = 0;
uint32_t lastCommand = 0xFFFFFFFF, lastReply = 0xFFFFFFFF;
uint32_t wordsOk = 0, wordsBad = 0;

void printReply(uint16_t w) {
  uint8_t top = w >> 12, hb = w >> 8, lb = w & 0xFF;
  if (top == 4) {                            // temperature: raw = 10-bit ADC reading of an NTC thermistor
    uint16_t raw = w & 0x0FFF;
    if (raw > 0 && raw < 1023) {
      float c = 4055.85f / (logf(1023.0f / raw - 1.0f) + 12.0813f) - 273.15f;
      Serial.printf("reply   0x%04X  temperature raw %u = %.0f C\n", w, raw, c);
    } else {
      Serial.printf("reply   0x%04X  temperature raw %u\n", w, raw);
    }
    return;
  }
  if (top != 6) { Serial.printf("reply   0x%04X  unknown\n", w); return; }
  if (lb == 0x0D || lb == 0x0C) Serial.printf("reply   0x%04X  stopped\n", w);   // 0x600C: single frames instead of 0x600D
  else if ((lb & 0xC0) == 0xC0) Serial.printf("reply   0x%04X  purge\n", w);
  else if ((lb & 0xC0) == 0x40)
    Serial.printf("reply   0x%04X  %s, level %u\n", w, (hb == 0x6C || hb == 0x6D) ? "running" : "starting", (lb & 0x0F) + 1);
  else Serial.printf("reply   0x%04X  unknown state\n", w);
}

void wordDone() {
  if (nbits == 0) return;
  if (bad || nbits > 32) { wordsBad++; return; }
  wordsOk++;
  if (nbits == 8) {                          // command from the controller: printed when it changes
    if (value != lastCommand) { lastCommand = value; Serial.printf("command 0x%02X\n", (unsigned) value); }
  } else if (nbits == 16) {                  // reply from the heater: state words when they change, temperature always
    if (value != lastReply || (value >> 12) == 4) { lastReply = value; printReply((uint16_t) value); }
  } else {
    Serial.printf("word of %u bits: 0x%X\n", (unsigned) nbits, (unsigned) value);
  }
}

void decode() {
  uint32_t h = head;
  if (h - tail > RING) { tail = h - RING; inWord = false; havePrev = false; }      // overflow: start again
  for (; tail != h; tail++) {
    uint32_t t = edgeTime[tail % RING];
    uint8_t level = edgeLevel[tail % RING];
    if (!havePrev) { havePrev = true; prevLevel = level; prevTime = t; continue; }
    if (level == prevLevel) { bad = true; continue; }                              // a missed glitch
    uint32_t d = t - prevTime;
    if (prevLevel == 1) {                    // a HIGH level ended
      highUs = d;
    } else {                                 // a LOW level ended
      if (d >= 20000) {                      // sync: the previous word is complete, a new one starts
        if (inWord) wordDone();
        inWord = true; nbits = 0; value = 0; bad = false;
      } else if (inWord) {
        if (highUs < 1500 || d < 1500) bad = true;
        if (nbits < 32) value = (value << 1) | (highUs > d ? 1 : 0);               // compare high with low
        nbits++;
      }
    }
    prevLevel = level;
    prevTime = t;
  }
  // inside a word the line is never high for more than 8 ms: after 15 ms of high the word is complete
  if (inWord && nbits > 0 && prevLevel == 1 && (uint32_t) (micros() - prevTime) > 15000) {
    wordDone();
    inWord = false; nbits = 0; value = 0;
  }
}

// ---- transmitter ----------------------------------------------------------------------------------------------
uint8_t pending = 0;                         // command waiting for a free moment on the line
uint32_t lastSendMs = 0;

void holdUs(uint32_t us) { uint32_t t0 = micros(); while ((uint32_t) (micros() - t0) < us) {} }

void sendCommand(uint8_t cmd) {
  sending = true;
  digitalWrite(PIN, HIGH);
  pinMode(PIN, OUTPUT);
  holdUs(20000);
  digitalWrite(PIN, LOW);  holdUs(30000);                    // sync
  for (int i = 7; i >= 0; i--) {
    bool one = (cmd >> i) & 1;
    digitalWrite(PIN, HIGH); holdUs(one ? 8000 : 4000);
    digitalWrite(PIN, LOW);  holdUs(one ? 4000 : 8000);
  }
  digitalWrite(PIN, HIGH); holdUs(1500);
  pinMode(PIN, INPUT);                                       // release the line: the heater answers 1-2 ms later
  noInterrupts();
  tail = head; havePrev = false; inWord = false;             // forget our own frame, decode the reply from scratch
  lastEdgeUs = micros();
  sending = false;
  interrupts();
  lastSendMs = millis();
  Serial.printf("sent    0x%02X\n", cmd);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN), onEdge, CHANGE);
  Serial.println("blue wire monitor: t = temperature, + / - = level, P = power toggle, s = status");
}

void loop() {
  decode();

  while (Serial.available()) {
    char c = (char) Serial.read();
    if (c == 't') pending = 0xAF;
    else if (c == '+') pending = 0xA3;
    else if (c == '-') pending = 0xA4;
    else if (c == 'P') pending = 0xA2;
    else if (c == 's') pending = 0xA6;
  }

  // Send only when the line is free: either no controller on the line (no edges for 1.5 s), or in the pause
  // between controller frames, 80-250 ms after the last edge (the pause is about 650 ms, our frame with the
  // reply takes about 370 ms). And not more often than once per second.
  if (pending != 0 && millis() - lastSendMs >= 1000) {
    uint32_t age = micros() - lastEdgeUs;
    if (age >= 1500000u || (age >= 80000u && age < 250000u)) {
      uint8_t cmd = pending;
      pending = 0;
      sendCommand(cmd);
    }
  }
}
