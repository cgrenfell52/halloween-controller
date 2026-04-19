/*
  Halloween Prop Controller Firmware
  Matches Python controller protocol: PROP_CTRL_V2

  Supported commands:
    SYS:PING
    SYS:STATUS
    SYS:STOP
    SYS:RESET
    SYS:ALL_OFF

    TOGGLE:HEAD_1
    TOGGLE:HEAD_2
    TOGGLE:AIR_CANNON
    TOGGLE:AIR_TICKLER
    TOGGLE:DOOR
    TOGGLE:HORN
    TOGGLE:CRACKLER
    TOGGLE:STROBE
    TOGGLE:FOG

    RUN:TRICK_HEAD_1
    RUN:TRICK_HEAD_2
    RUN:TRICK_HORN
    RUN:TRICK_CRACKLER
    RUN:TRICK_AIR_CANNON
    RUN:TRICK_BOTH_HEADS
    RUN:DOOR_SEQUENCE
    RUN:FOG_BURST

  Serial:
    115200 baud
    newline-terminated commands
*/

#include <Arduino.h>

// --------------------------------------------------
// CONFIG
// --------------------------------------------------
static const unsigned long SERIAL_BAUD = 115200;
static const char* PROTOCOL_VERSION = "PROP_CTRL_V2";

static const uint8_t OUTPUT_COUNT = 9;

enum OutputIndex : uint8_t {
  OUT_HEAD_1 = 0,
  OUT_HEAD_2,
  OUT_AIR_CANNON,
  OUT_AIR_TICKLER,
  OUT_DOOR,
  OUT_HORN,
  OUT_CRACKLER,
  OUT_STROBE,
  OUT_FOG
};

const char* OUTPUT_NAMES[OUTPUT_COUNT] = {
  "HEAD_1",
  "HEAD_2",
  "AIR_CANNON",
  "AIR_TICKLER",
  "DOOR",
  "HORN",
  "CRACKLER",
  "STROBE",
  "FOG",
};

// Current default mapping from the controller-side names
const uint8_t OUTPUT_PINS[OUTPUT_COUNT] = {
  4,   // HEAD_1 / Skinny
  5,   // HEAD_2 / Hag
  6,   // AIR_CANNON
  7,   // AIR_TICKLER
  8,   // DOOR
  9,   // HORN / Ooga
  10,  // CRACKLER
  13,  // STROBE
  22   // FOG
};

bool outputStates[OUTPUT_COUNT] = {false, false, false, false, false, false, false, false, false};

enum SystemStatus {
  STATUS_IDLE = 0,
  STATUS_RUNNING_SCENE,
  STATUS_RUNNING_SERVICE,
  STATUS_STOPPING,
  STATUS_RESETTING
};

SystemStatus systemStatus = STATUS_IDLE;
String currentAction = "NONE";
bool stopRequested = false;

// --------------------------------------------------
// SCENE TIMINGS
// --------------------------------------------------
static const unsigned long DURATION_TRICK_HEAD_1    = 1200;
static const unsigned long DURATION_TRICK_HEAD_2    = 1200;
static const unsigned long DURATION_TRICK_HORN      = 900;
static const unsigned long DURATION_TRICK_CRACKLER  = 900;
static const unsigned long DURATION_TRICK_AIR       = 300;
static const unsigned long DURATION_TRICK_BOTH      = 2000;
static const unsigned long DURATION_DOOR_HOLD_TOTAL = 22000;
static const unsigned long DURATION_DOOR_TICKLE_PRE = 10000;
static const uint8_t DOOR_TICKLE_COUNT = 5;
static const unsigned long DURATION_DOOR_TICKLE_ON_MIN  = 350;
static const unsigned long DURATION_DOOR_TICKLE_ON_MAX  = 700;
static const unsigned long DURATION_DOOR_TICKLE_GAP_MIN = 500;
static const unsigned long DURATION_DOOR_TICKLE_GAP_MAX = 4000;
static const unsigned long DURATION_FOG_BURST       = 10000;

// --------------------------------------------------
// SERIAL BUFFER
// --------------------------------------------------
String inputBuffer;

// --------------------------------------------------
// HELPERS
// --------------------------------------------------
const char* systemStatusToText(SystemStatus s) {
  switch (s) {
    case STATUS_IDLE:            return "IDLE";
    case STATUS_RUNNING_SCENE:   return "RUNNING_SCENE";
    case STATUS_RUNNING_SERVICE: return "RUNNING_SERVICE";
    case STATUS_STOPPING:        return "STOPPING";
    case STATUS_RESETTING:       return "RESETTING";
    default:                     return "ERROR";
  }
}

void sendLine(const String& line) {
  Serial.println(line);
}

void sendReady() {
  sendLine(String("READY:") + PROTOCOL_VERSION);
}

void sendPong() {
  sendLine("PONG");
}

void sendStatus() {
  if (currentAction == "NONE" || currentAction.length() == 0) {
    sendLine(String("STATUS:") + systemStatusToText(systemStatus));
  } else {
    sendLine(String("STATUS:") + systemStatusToText(systemStatus) + ":" + currentAction);
  }
}

void sendStateByIndex(uint8_t idx) {
  if (idx >= OUTPUT_COUNT) return;
  sendLine(String("STATE:") + OUTPUT_NAMES[idx] + ":" + (outputStates[idx] ? "ON" : "OFF"));
}

void sendAllStates() {
  for (uint8_t i = 0; i < OUTPUT_COUNT; i++) {
    sendStateByIndex(i);
  }
}

int findOutputIndexByName(const String& name) {
  for (uint8_t i = 0; i < OUTPUT_COUNT; i++) {
    if (name.equalsIgnoreCase(OUTPUT_NAMES[i])) {
      return i;
    }
  }
  return -1;
}

void setOutputRaw(uint8_t idx, bool on) {
  if (idx >= OUTPUT_COUNT) return;
  outputStates[idx] = on;
  digitalWrite(OUTPUT_PINS[idx], on ? HIGH : LOW);
}

void setOutputAndReport(uint8_t idx, bool on) {
  setOutputRaw(idx, on);
  sendStateByIndex(idx);
}

void allOutputsOffNoReport() {
  for (uint8_t i = 0; i < OUTPUT_COUNT; i++) {
    setOutputRaw(i, false);
  }
}

void allOutputsOffAndReport() {
  for (uint8_t i = 0; i < OUTPUT_COUNT; i++) {
    setOutputRaw(i, false);
    sendStateByIndex(i);
  }
}

void setSystemStatus(SystemStatus newStatus, const String& action) {
  systemStatus = newStatus;
  currentAction = action;
  sendStatus();
}

void forceIdleStatus() {
  systemStatus = STATUS_IDLE;
  currentAction = "NONE";
  sendStatus();
}

void finishAndReturnIdle(const String& doneText) {
  currentAction = "NONE";
  sendLine(doneText);
  systemStatus = STATUS_IDLE;
  sendStatus();
}

void reportError(const String& err) {
  sendLine(err);
}

bool isControllerBusy() {
  return systemStatus != STATUS_IDLE;
}

// --------------------------------------------------
// SAFE ABORT / SYS COMMAND RESPONSES
// --------------------------------------------------
void doStopLikeResponse(const String& doneText, SystemStatus transientStatus) {
  stopRequested = true;
  setSystemStatus(transientStatus, "NONE");
  allOutputsOffAndReport();
  stopRequested = false;
  finishAndReturnIdle(doneText);
}

void handleSysPing() {
  sendReady();
  sendPong();
}

void handleSysStatus() {
  sendStatus();
}

void handleSysStop() {
  doStopLikeResponse("DONE:SYS:STOP", STATUS_STOPPING);
}

void handleSysReset() {
  doStopLikeResponse("DONE:SYS:RESET", STATUS_RESETTING);
}

void handleSysAllOff() {
  doStopLikeResponse("DONE:SYS:ALL_OFF", STATUS_STOPPING);
}

// --------------------------------------------------
// SERIAL POLLING
// --------------------------------------------------
void handleBackgroundCommand(const String& cmd);

void pollSerialInputNonBlocking() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      String cmd = inputBuffer;
      inputBuffer = "";
      cmd.trim();

      if (cmd.length() > 0) {
        handleBackgroundCommand(cmd);
      }
    } else {
      inputBuffer += c;
      if (inputBuffer.length() > 120) {
        inputBuffer.remove(0, inputBuffer.length() - 120);
      }
    }
  }
}

bool waitWithPolling(unsigned long durationMs) {
  unsigned long start = millis();

  while ((millis() - start) < durationMs) {
    pollSerialInputNonBlocking();

    if (stopRequested) {
      return false;
    }

    delay(5);
  }

  return true;
}

// --------------------------------------------------
// SCENES
// --------------------------------------------------
bool runScene_TRICK_HEAD_1() {
  setOutputRaw(OUT_HEAD_1, true);
  sendStateByIndex(OUT_HEAD_1);
  bool ok = waitWithPolling(DURATION_TRICK_HEAD_1);
  setOutputRaw(OUT_HEAD_1, false);
  sendStateByIndex(OUT_HEAD_1);
  return ok;
}

bool runScene_TRICK_HEAD_2() {
  setOutputRaw(OUT_HEAD_2, true);
  sendStateByIndex(OUT_HEAD_2);
  bool ok = waitWithPolling(DURATION_TRICK_HEAD_2);
  setOutputRaw(OUT_HEAD_2, false);
  sendStateByIndex(OUT_HEAD_2);
  return ok;
}

bool runScene_TRICK_HORN() {
  setOutputRaw(OUT_HORN, true);
  sendStateByIndex(OUT_HORN);
  bool ok = waitWithPolling(DURATION_TRICK_HORN);
  setOutputRaw(OUT_HORN, false);
  sendStateByIndex(OUT_HORN);
  return ok;
}

bool runScene_TRICK_CRACKLER() {
  setOutputRaw(OUT_CRACKLER, true);
  sendStateByIndex(OUT_CRACKLER);
  bool ok = waitWithPolling(DURATION_TRICK_CRACKLER);
  setOutputRaw(OUT_CRACKLER, false);
  sendStateByIndex(OUT_CRACKLER);
  return ok;
}

bool runScene_TRICK_AIR_CANNON() {
  setOutputRaw(OUT_AIR_CANNON, true);
  sendStateByIndex(OUT_AIR_CANNON);
  bool ok = waitWithPolling(DURATION_TRICK_AIR);
  setOutputRaw(OUT_AIR_CANNON, false);
  sendStateByIndex(OUT_AIR_CANNON);
  return ok;
}

bool runScene_TRICK_BOTH_HEADS() {
  setOutputRaw(OUT_HEAD_1, true);
  setOutputRaw(OUT_HEAD_2, true);
  sendStateByIndex(OUT_HEAD_1);
  sendStateByIndex(OUT_HEAD_2);

  bool ok = waitWithPolling(DURATION_TRICK_BOTH);

  setOutputRaw(OUT_HEAD_1, false);
  setOutputRaw(OUT_HEAD_2, false);
  sendStateByIndex(OUT_HEAD_1);
  sendStateByIndex(OUT_HEAD_2);
  return ok;
}

bool runScene_DOOR_SEQUENCE() {
  setOutputRaw(OUT_DOOR, true);
  sendStateByIndex(OUT_DOOR);
  unsigned long doorElapsed = 0;

  if (!waitWithPolling(DURATION_DOOR_TICKLE_PRE)) {
    setOutputRaw(OUT_DOOR, false);
    sendStateByIndex(OUT_DOOR);
    return false;
  }
  doorElapsed += DURATION_DOOR_TICKLE_PRE;

  for (uint8_t i = 0; i < DOOR_TICKLE_COUNT; i++) {
    unsigned long tickleOn = random(DURATION_DOOR_TICKLE_ON_MIN, DURATION_DOOR_TICKLE_ON_MAX + 1);
    setOutputRaw(OUT_AIR_TICKLER, true);
    sendStateByIndex(OUT_AIR_TICKLER);
    if (!waitWithPolling(tickleOn)) {
      setOutputRaw(OUT_AIR_TICKLER, false);
      setOutputRaw(OUT_DOOR, false);
      sendStateByIndex(OUT_AIR_TICKLER);
      sendStateByIndex(OUT_DOOR);
      return false;
    }
    doorElapsed += tickleOn;

    setOutputRaw(OUT_AIR_TICKLER, false);
    sendStateByIndex(OUT_AIR_TICKLER);

    if (i < DOOR_TICKLE_COUNT - 1) {
      unsigned long tickleGap = random(DURATION_DOOR_TICKLE_GAP_MIN, DURATION_DOOR_TICKLE_GAP_MAX + 1);
      if (!waitWithPolling(tickleGap)) {
        setOutputRaw(OUT_DOOR, false);
        sendStateByIndex(OUT_DOOR);
        return false;
      }
      doorElapsed += tickleGap;
    }
  }

  const unsigned long finalHold =
      DURATION_DOOR_HOLD_TOTAL > doorElapsed
          ? DURATION_DOOR_HOLD_TOTAL - doorElapsed
          : 0;

  if (finalHold > 0 && !waitWithPolling(finalHold)) {
    setOutputRaw(OUT_DOOR, false);
    sendStateByIndex(OUT_DOOR);
    return false;
  }

  setOutputRaw(OUT_DOOR, false);
  sendStateByIndex(OUT_DOOR);
  return true;
}

bool runScene_FOG_BURST() {
  setOutputRaw(OUT_FOG, true);
  sendStateByIndex(OUT_FOG);
  bool ok = waitWithPolling(DURATION_FOG_BURST);
  setOutputRaw(OUT_FOG, false);
  sendStateByIndex(OUT_FOG);
  return ok;
}

bool executeSceneByName(const String& sceneName) {
  if (sceneName.equalsIgnoreCase("TRICK_HEAD_1"))      return runScene_TRICK_HEAD_1();
  if (sceneName.equalsIgnoreCase("TRICK_HEAD_2"))      return runScene_TRICK_HEAD_2();
  if (sceneName.equalsIgnoreCase("TRICK_HORN"))        return runScene_TRICK_HORN();
  if (sceneName.equalsIgnoreCase("TRICK_CRACKLER"))    return runScene_TRICK_CRACKLER();
  if (sceneName.equalsIgnoreCase("TRICK_AIR_CANNON"))  return runScene_TRICK_AIR_CANNON();
  if (sceneName.equalsIgnoreCase("TRICK_BOTH_HEADS"))  return runScene_TRICK_BOTH_HEADS();
  if (sceneName.equalsIgnoreCase("DOOR_SEQUENCE"))     return runScene_DOOR_SEQUENCE();
  if (sceneName.equalsIgnoreCase("FOG_BURST"))         return runScene_FOG_BURST();

  reportError("ERROR:UNKNOWN_SCENE");
  return false;
}

// --------------------------------------------------
// COMMAND HANDLERS
// --------------------------------------------------
void handleToggleCommand(const String& outputName) {
  if (isControllerBusy()) {
    reportError("ERROR:BUSY");
    return;
  }

  int idx = findOutputIndexByName(outputName);
  if (idx < 0) {
    reportError("ERROR:UNKNOWN_COMMAND");
    return;
  }

  setSystemStatus(STATUS_RUNNING_SERVICE, outputName);

  bool newState = !outputStates[idx];
  setOutputAndReport((uint8_t)idx, newState);

  finishAndReturnIdle(String("DONE:TOGGLE:") + OUTPUT_NAMES[idx]);
}

void handleRunCommand(const String& sceneName) {
  if (isControllerBusy()) {
    reportError("ERROR:BUSY");
    return;
  }

  setSystemStatus(STATUS_RUNNING_SCENE, sceneName);
  stopRequested = false;

  bool ok = executeSceneByName(sceneName);

  if (stopRequested) {
    allOutputsOffAndReport();
    stopRequested = false;
    finishAndReturnIdle(String("DONE:") + sceneName);
    return;
  }

  if (!ok) {
    allOutputsOffAndReport();
    forceIdleStatus();
    return;
  }

  finishAndReturnIdle(String("DONE:") + sceneName);
}

void handleCommand(const String& rawCmd) {
  String cmd = rawCmd;
  cmd.trim();

  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("SYS:PING")) {
    handleSysPing();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:STATUS")) {
    handleSysStatus();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:STOP")) {
    handleSysStop();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:RESET")) {
    handleSysReset();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:ALL_OFF")) {
    handleSysAllOff();
    return;
  }

  if (cmd.startsWith("TOGGLE:")) {
    String name = cmd.substring(7);
    name.trim();
    handleToggleCommand(name);
    return;
  }

  if (cmd.startsWith("RUN:")) {
    String sceneName = cmd.substring(4);
    sceneName.trim();
    handleRunCommand(sceneName);
    return;
  }

  reportError("ERROR:UNKNOWN_COMMAND");
}

// This is the important fix area:
// system commands now always respond immediately even during a scene.
void handleBackgroundCommand(const String& rawCmd) {
  String cmd = rawCmd;
  cmd.trim();

  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("SYS:PING")) {
    handleSysPing();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:STATUS")) {
    handleSysStatus();
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:STOP")) {
    stopRequested = true;
    doStopLikeResponse("DONE:SYS:STOP", STATUS_STOPPING);
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:RESET")) {
    stopRequested = true;
    doStopLikeResponse("DONE:SYS:RESET", STATUS_RESETTING);
    return;
  }

  if (cmd.equalsIgnoreCase("SYS:ALL_OFF")) {
    stopRequested = true;
    doStopLikeResponse("DONE:SYS:ALL_OFF", STATUS_STOPPING);
    return;
  }

  if (systemStatus == STATUS_RUNNING_SCENE || systemStatus == STATUS_RUNNING_SERVICE) {
    reportError("ERROR:BUSY");
    return;
  }

  handleCommand(cmd);
}

// --------------------------------------------------
// SETUP / LOOP
// --------------------------------------------------
void setup() {
  Serial.begin(SERIAL_BAUD);

  for (uint8_t i = 0; i < OUTPUT_COUNT; i++) {
    pinMode(OUTPUT_PINS[i], OUTPUT);
    digitalWrite(OUTPUT_PINS[i], LOW);
    outputStates[i] = false;
  }

  systemStatus = STATUS_IDLE;
  currentAction = "NONE";
  stopRequested = false;
  inputBuffer.reserve(128);

  delay(100);
  sendReady();
  sendStatus();
  sendAllStates();
}

void loop() {
  pollSerialInputNonBlocking();
}
