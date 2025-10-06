#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>

#include "colour_bars_16b.h"   
#include "colour_gradients.h"   
#include "grid_16b.h"   
#include "circles.h"   

// PAL
M5UnitRCA RcaOutput ( 360                            // logical_width
                  , 240                            // logical_height
                  , 384                            // output_width
                  , 288                            // output_height
                  , M5UnitRCA::signal_type_t::PAL // signal_type
                  , M5UnitRCA::use_psram_t::psram_use
                  , 26                             // GPIO pin
                  , 128
                  );

                  // NTSC
// M5UnitRCA RcaOutput ( 360                            // logical_width
//                   , 240                            // logical_height
//                   , 360                            // output_width
//                   , 240                           // output_height
//                   , M5UnitRCA::signal_type_t::NTSC // signal_type
//                   , M5UnitRCA::use_psram_t::psram_use
//                   , 26                             // GPIO pin
//                   , 128
//                   );

void setup() {
  M5.begin();

  M5.Display.setTextSize(2);
  M5.Display.clear(); 
  
  RcaOutput.setOutputBoost(true);
  RcaOutput.init();
  RcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_nonswapped);
}

void loop() {
  Serial.println("Working");

  // M5.Display.clear();
  // M5.Display.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)grid_bmp);
  // M5.Display.drawString("GRID", M5.Display.width() / 4, M5.Display.height() / 2);
  // RcaOutput.clear();
  // RcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)grid_bmp);
  // delay(2000);

  M5.Display.clear();
  M5.Display.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
  M5.Display.drawString("BARS", M5.Display.width() / 4, M5.Display.height() / 2);
  RcaOutput.clear();
  RcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t*)colour_bars_png);
  delay(2000);

  // M5.Display.clear();
  // M5.Display.drawRect(0, 0, 320, 240, TFT_RED);
  // M5.Display.drawRect(10, 10, 300, 220, TFT_GREEN);
  // M5.Display.drawRect(20, 20, 280, 200, TFT_BLUE);
  // M5.Display.drawRect(30, 30, 260, 180, TFT_CYAN);
  // M5.Display.drawRect(40, 40, 240, 160, TFT_MAGENTA);
  // M5.Display.drawRect(50, 50, 220, 140, TFT_YELLOW);
  // M5.Display.fillCircle(160, 120, 5, TFT_WHITE);
  // RcaOutput.clear();
  // RcaOutput.drawRect(0, 0, 320, 240, TFT_RED);
  // RcaOutput.drawRect(10, 10, 300, 220, TFT_GREEN);
  // RcaOutput.drawRect(20, 20, 280, 200, TFT_BLUE);
  // RcaOutput.drawRect(30, 30, 260, 180, TFT_CYAN);
  // RcaOutput.drawRect(40, 40, 240, 160, TFT_MAGENTA);
  // RcaOutput.drawRect(50, 50, 220, 140, TFT_YELLOW);
  // RcaOutput.fillCircle(160, 120, 5, TFT_WHITE);
  // delay(2000);

  M5.Display.clear();
  M5.Display.drawPng(colour_gradients_png, colour_gradients_png_len, 0, 0);
  M5.Display.drawString("GRADIENTS", M5.Display.width() / 4, M5.Display.height() / 2);
  RcaOutput.clear();
  RcaOutput.drawPng(colour_gradients_png, colour_gradients_png_len, 0, 0);
  delay(2000);
  
}
