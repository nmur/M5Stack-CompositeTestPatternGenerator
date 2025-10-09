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

Preferences preferences;

const int VIDEO_MODE_BUTTON_PIN = 39;  
bool _videoModeLastButtonState = HIGH;     
bool _isPalMode = false;

M5UnitRCA RcaOutput(360,                           // logical_width
                    240,                           // logical_height
                    384,                             // output_width (will be set in setup)
                    288,                             // output_height (will be set in setup)
                    M5UnitRCA::signal_type_t::PAL, // signal_type (will be updated in setup)
                    M5UnitRCA::use_psram_t::psram_use,
                    26,                            // GPIO pin
                    128);

void saveIsPalState(bool isPalMode)
{
  preferences.begin("video", false);
  preferences.putBool("isPal", isPalMode);
  preferences.end();
}

void loadIsPalState()
{
  preferences.begin("video", false);
  _isPalMode = preferences.getBool("isPal", true);
  preferences.end();
}

void toggleVideoMode() {
  saveIsPalState(!_isPalMode);
  restart();
}

void restart()
{
  ESP.restart();
}

void setup() {
  pinMode(VIDEO_MODE_BUTTON_PIN, INPUT_PULLUP);

  M5.begin();
  M5.Display.setTextSize(2);
  M5.Display.clear();

  InitRcaOutput();

  M5.Display.clear();
  M5.Display.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", M5.Display.width() / 4, M5.Display.height() / 2);
  RcaOutput.clear();
  RcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
}

void InitRcaOutput()
{
  loadIsPalState();
  SetRcaOutputVideoMode();

  RcaOutput.setOutputBoost(true);
  RcaOutput.init();
  RcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_nonswapped);
}

void SetRcaOutputVideoMode()
{
  if (_isPalMode)
  {
    RcaOutput = M5UnitRCA(360,                           // logical_width
                          240,                           // logical_height
                          384,                           // output_width
                          288,                           // output_height
                          M5UnitRCA::signal_type_t::PAL, // signal_type
                          M5UnitRCA::use_psram_t::psram_use,
                          26, // GPIO pin
                          128);
  }
  else
  {
    RcaOutput = M5UnitRCA(360,                            // logical_width
                          240,                            // logical_height
                          360,                            // output_width
                          240,                            // output_height
                          M5UnitRCA::signal_type_t::NTSC, // signal_type
                          M5UnitRCA::use_psram_t::psram_use,
                          26, // GPIO pin
                          128);
  }
}

void loop() {
  toggleVideoModeIfButtonPressed();

  delay(100);  
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
