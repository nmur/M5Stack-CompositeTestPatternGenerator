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

const int BUTTON_PIN = 39;  // GPIO39 for button input
bool lastButtonState = HIGH;     // For tracking button state changes
bool isPalMode = false;
M5UnitRCA RcaOutput(360,                           // logical_width
                    240,                           // logical_height
                    384,                             // output_width (will be set in setup)
                    288,                             // output_height (will be set in setup)
                    M5UnitRCA::signal_type_t::PAL, // signal_type (will be updated in setup)
                    M5UnitRCA::use_psram_t::psram_use,
                    26,                            // GPIO pin
                    128);

void toggleVideoMode() {
  // Save the new mode to NVS
  preferences.begin("video", false);
  preferences.putBool("isPal", !isPalMode);
  preferences.end();
  
  // Restart the device
  ESP.restart();
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);  // Enable pullup for button
  M5.begin();
  M5.Display.setTextSize(2);
  M5.Display.clear();

  // Read the saved mode from NVS
  preferences.begin("video", false);
  isPalMode = preferences.getBool("isPal", true); // Default to PAL if not set
  preferences.end();

  // Configure RCA output based on mode
  if (isPalMode) {
    RcaOutput = M5UnitRCA(360,                           // logical_width
                         240,                           // logical_height
                         384,                           // output_width
                         288,                           // output_height
                         M5UnitRCA::signal_type_t::PAL, // signal_type
                         M5UnitRCA::use_psram_t::psram_use,
                         26,                            // GPIO pin
                         128);
  } else {
    RcaOutput = M5UnitRCA(360,                           // logical_width
                         240,                           // logical_height
                         360,                           // output_width
                         240,                           // output_height
                         M5UnitRCA::signal_type_t::NTSC, // signal_type
                         M5UnitRCA::use_psram_t::psram_use,
                         26,                            // GPIO pin
                         128);
  }

  RcaOutput.setOutputBoost(true);
  RcaOutput.init();
  RcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_nonswapped);

  // Update display
  M5.Display.clear();
  M5.Display.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
  M5.Display.drawString(isPalMode ? "PAL" : "NTSC", M5.Display.width() / 4, M5.Display.height() / 2);
  RcaOutput.clear();
  RcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
}

void loop() {
  // Read the current button state
  bool currentButtonState = digitalRead(BUTTON_PIN);

  // Check for button press (transition from HIGH to LOW)
  if (currentButtonState == LOW && lastButtonState == HIGH) {
    delay(50);  // Simple debounce
    if (digitalRead(BUTTON_PIN) == LOW) {  // Confirm button is still pressed
      toggleVideoMode();
    }
  }
  lastButtonState = currentButtonState;
  
  delay(100);  // Small delay for stability
}