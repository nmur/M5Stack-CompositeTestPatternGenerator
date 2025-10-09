#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>
#include <Preferences.h>

#include "colour_bars_16b.h"   
#include "colour_gradients.h"   
#include "grid_16b.h"   
#include "circles.h"   

Preferences _preferences;

const int VIDEO_MODE_BUTTON_PIN = 39; // Button B
const int PATTERN_BUTTON_PIN = 37; // Button A

bool _videoModeLastButtonState = HIGH;     
bool _patternLastButtonState = HIGH;
bool _isPalMode = false;

const uint16_t* PATTERNS[] = {
  colour_bars_png, 
  grid_bmp
};
const int PATTERN_COUNT = 2;
int _currentPatternIndex = 0;

M5UnitRCA _rcaOutput;

M5UnitRCA GetPalRcaConfig();
M5UnitRCA GetPalNtscConfig();

void initLcdDisplay();
void initRcaOutput();
void loadVideoModeState();
void setRcaOutputVideoMode();

void restart();
void toggleVideoModeIfButtonPressed();
void toggleVideoMode();
void saveIsPalState(bool isPalMode);

void displayPattern(const uint16_t* imageData);
void cyclePattern();
void checkPatternButton();

M5UnitRCA GetPalRcaConfig()
{
  return M5UnitRCA(360, 240,
                   384, 288,
                   M5UnitRCA::signal_type_t::PAL, 
                   M5UnitRCA::use_psram_t::psram_use,
                   26, 
                   128);
}

M5UnitRCA GetPalNtscConfig()
{
  return M5UnitRCA(360, 240,
                   360, 240,
                   M5UnitRCA::signal_type_t::NTSC, 
                   M5UnitRCA::use_psram_t::psram_use,
                   26, 
                   128);
}

void initLcdDisplay()
{
  M5.begin();
  M5.Display.setTextSize(2);
  M5.Display.clear();
}

void loadVideoModeState()
{
  _preferences.begin("video", false);
  _isPalMode = _preferences.getBool("isPal", true);
  _preferences.end();
}

void setRcaOutputVideoMode()
{
  if (_isPalMode)
  {
    _rcaOutput = GetPalRcaConfig();
  }
  else
  {
    _rcaOutput = GetPalNtscConfig();
  }
}

void initRcaOutput()
{
  loadVideoModeState();
  setRcaOutputVideoMode();

  _rcaOutput.setOutputBoost(true);
  _rcaOutput.init();
  _rcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_nonswapped);
}

void displayPattern(const uint16_t* imageData)
{
  M5.Display.clear();
  M5.Display.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t *)imageData);
  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", M5.Display.width() / 4, M5.Display.height() / 2 + 30);
  _rcaOutput.clear();
  _rcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t *)imageData);
}

void saveIsPalState(bool isPalMode)
{
  _preferences.begin("video", false);
  _preferences.putBool("isPal", isPalMode);
  _preferences.end();
}

void restart()
{
  ESP.restart();
}

void toggleVideoMode() {
  saveIsPalState(!_isPalMode);
  restart();
}

void toggleVideoModeIfButtonPressed()
{
  bool currentButtonState = digitalRead(VIDEO_MODE_BUTTON_PIN);

  if (currentButtonState == LOW && _videoModeLastButtonState == HIGH)
  {
    delay(50);
    if (digitalRead(VIDEO_MODE_BUTTON_PIN) == LOW)
    {
      toggleVideoMode();
    }
  }
  _videoModeLastButtonState = currentButtonState;
}

void cyclePattern()
{
  _currentPatternIndex = (_currentPatternIndex + 1) % PATTERN_COUNT;
  displayPattern(PATTERNS[_currentPatternIndex]);
}

void checkPatternButton()
{
  bool currentButtonState = digitalRead(PATTERN_BUTTON_PIN);

  if (currentButtonState == LOW && _patternLastButtonState == HIGH)
  {
    delay(50);  
    if (digitalRead(PATTERN_BUTTON_PIN) == LOW)
    {
      cyclePattern();
    }
  }
  _patternLastButtonState = currentButtonState;
}

void setup() {
  pinMode(VIDEO_MODE_BUTTON_PIN, INPUT_PULLUP);
  pinMode(PATTERN_BUTTON_PIN, INPUT_PULLUP);

  initLcdDisplay();
  initRcaOutput();

  displayPattern(colour_bars_png);
}

void loop() {
  toggleVideoModeIfButtonPressed();
  checkPatternButton();

  delay(100);  
}
