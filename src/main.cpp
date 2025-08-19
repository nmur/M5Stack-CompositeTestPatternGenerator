#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>

#include "colour_bars.h"   
#include "colour_gradients.h"   
#include "grid.h"   
#include "circles.h"   

M5ModuleRCA RcaOutput ( 360                            // logical_width
                  , 240                            // logical_height
                  , 360                            // output_width
                  , 240                            // output_height
                  , M5ModuleRCA::signal_type_t::PAL // signal_type
                  , M5ModuleRCA::use_psram_t::psram_half_use
                  , 26                             // GPIO pin
                  , 200
                  );

void setup() {
  M5.begin();

  M5.Display.setTextSize(2);
  M5.Display.clear();

  RcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_2Byte);
  RcaOutput.init();
}

void loop() {

    Serial.println("Working");
    M5.Display.clear();
    M5.Display.drawPng(colour_gradients_png, colour_gradients_png_len, 0, 0);
    M5.Display.drawString("GRADIENTS", M5.Display.width() / 4, M5.Display.height() / 2);
    RcaOutput.clear();
    RcaOutput.drawPng(colour_gradients_png, colour_gradients_png_len, 0, 0);
    delay(2000);
    M5.Display.clear();
    M5.Display.drawPng(circles_png, circles_png_len, 0, 0);
    M5.Display.drawString("CIRCLES", M5.Display.width() / 4, M5.Display.height() / 2);
    RcaOutput.clear();
    RcaOutput.drawPng(circles_png, circles_png_len, 0, 0);
    delay(2000);
    M5.Display.clear();
    M5.Display.drawPng(grid_png, grid_png_len, 0, 0);
    M5.Display.drawString("GRID", M5.Display.width() / 4, M5.Display.height() / 2);
    RcaOutput.clear();
    RcaOutput.drawPng(grid_png, grid_png_len, 0, 0);
    delay(2000);
    M5.Display.clear();
    M5.Display.drawPng(colour_bars_png, colour_bars_png_len, 0, 0);
    M5.Display.drawString("BARS", M5.Display.width() / 4, M5.Display.height() / 2);
    RcaOutput.clear();
    RcaOutput.drawPng(colour_bars_png, colour_bars_png_len, 0, 0);
    delay(2000);
}
