#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>

M5ModuleRCA display ( 360                            // logical_width
                  , 240                            // logical_height
                  , 360                            // output_width
                  , 240                            // output_height
                  , M5ModuleRCA::signal_type_t::PAL // signal_type
                  , M5ModuleRCA::use_psram_t::psram_half_use
                  , 26                             // GPIO pin
                  , 128
                  );

void setup() {
  M5.begin();

  M5.Display.setTextSize(2);
  M5.Display.clear(TFT_SKYBLUE);
  M5.Display.drawString("BEGIN!", M5.Display.width() / 4, M5.Display.height() / 2);

  display.setColorDepth(m5gfx::color_depth_t::rgb565_2Byte);
  display.init();
  display.fillScreen(TFT_BLUE);

  delay(5000);
}

void loop() {

    Serial.println("Working");
    delay(2000);
    M5.Display.clear(TFT_RED);
    display.fillScreen(TFT_RED);
    M5.Display.drawString("RED", M5.Display.width() / 4, M5.Display.height() / 2);
    delay(2000);
    M5.Display.clear(TFT_GREEN);
    display.fillScreen(TFT_GREEN);
    M5.Display.drawString("GREEN", M5.Display.width() / 4, M5.Display.height() / 2);
    delay(2000);
    M5.Display.clear(TFT_BLUE);
    display.fillScreen(TFT_BLUE);
    M5.Display.drawString("BLUE", M5.Display.width() / 4, M5.Display.height() / 2);
    delay(2000);
    M5.Display.clear(TFT_WHITE);
    display.fillScreen(TFT_WHITE);
    M5.Display.drawString("WHITE", M5.Display.width() / 4, M5.Display.height() / 2);
}
