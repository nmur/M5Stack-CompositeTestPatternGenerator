#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>
#include <Preferences.h>

#include "colour_bars.h"   
#include "grid.h"   
#include "circles.h"
#include "gradients.h"
#include "white.h"
// Not enough memory to include all patterns as raw bmp arrays for now
// #include "red.h"
// #include "green.h"
// #include "blue.h"

Preferences _preferences;

const int VIDEO_MODE_BUTTON_PIN = 39; // Button B
const int PATTERN_BUTTON_PIN = 37; // Button A

bool _videoModeLastButtonState = HIGH;     
bool _patternLastButtonState = HIGH;
bool _isPalMode = false;

const uint16_t* PATTERNS[] = {
  colour_bars_bmp, 
  grid_bmp, 
  circles_bmp,
  gradients_bmp,
  white_bmp,
  // red_bmp,
  // green_bmp,
  // blue_bmp
};
const int PATTERN_COUNT = 5;
int _currentPatternIndex = 0;

M5UnitRCA _rcaOutput;

M5UnitRCA GetPalRcaConfig();
M5UnitRCA GetNtscRcaConfig();

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
  return M5UnitRCA(384, 288,
                   384, 288,
                   M5UnitRCA::signal_type_t::PAL, 
                   M5UnitRCA::use_psram_t::psram_use,
                   26, 
                   128);
}

M5UnitRCA GetNtscRcaConfig()
{
  return M5UnitRCA(320, 240,
                   320, 240,
                   M5UnitRCA::signal_type_t::NTSC, 
                   M5UnitRCA::use_psram_t::psram_use,
                   26, 
                   128);
}

void initLcdDisplay()
{
  M5.begin();
  M5.Display.setTextSize(2);
  M5.Display.setRotation(1);
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
    _rcaOutput = GetNtscRcaConfig();
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

uint16_t* ScaleImage50Percent(const uint16_t* imageData) {
  uint16_t* out = (uint16_t*) malloc(19200 * sizeof(uint16_t));
  if (!out) return nullptr;
  size_t index = 0;
  for (int y = 0; y < 240; y += 2) {
    for (int x = 0; x < 320; x += 2) {
      out[index++] = imageData[y * 320 + x];
    }
  }
  return out; 
}

uint16_t* ScaleImageForPalBilinear(const uint16_t* imageData) {
  const int srcW = 320;
  const int srcH = 240;
  const int dstW = 384;
  const int dstH = 288;
  uint16_t* out = (uint16_t*) malloc(dstW * dstH * sizeof(uint16_t));
  if (!out) return nullptr;
  // Precompute fixed-point scale (16.16)
  const uint32_t xScale = ((uint32_t)(srcW - 1) << 16) / (dstW - 1);
  const uint32_t yScale = ((uint32_t)(srcH - 1) << 16) / (dstH - 1);
  for (int y = 0; y < dstH; ++y) {
    uint32_t fy = y * yScale;
    int y0 = fy >> 16;
    int y1 = (y0 < srcH - 1) ? (y0 + 1) : y0;
    uint32_t wy = fy & 0xFFFF;          // 0..65535
    uint32_t wy0 = 65536 - wy;
    uint32_t wy1 = wy;
    for (int x = 0; x < dstW; ++x) {
      uint32_t fx = x * xScale;
      int x0 = fx >> 16;
      int x1 = (x0 < srcW - 1) ? (x0 + 1) : x0;
      uint32_t wx = fx & 0xFFFF;        // 0..65535
      uint32_t wx0 = 65536 - wx;
      uint32_t wx1 = wx;
      uint16_t c00 = imageData[y0 * srcW + x0];
      uint16_t c10 = imageData[y0 * srcW + x1];
      uint16_t c01 = imageData[y1 * srcW + x0];
      uint16_t c11 = imageData[y1 * srcW + x1];
      // Expand RGB565
      uint32_t r00 = (c00 >> 11) & 0x1F, g00 = (c00 >> 5) & 0x3F, b00 = c00 & 0x1F;
      uint32_t r10 = (c10 >> 11) & 0x1F, g10 = (c10 >> 5) & 0x3F, b10 = c10 & 0x1F;
      uint32_t r01 = (c01 >> 11) & 0x1F, g01 = (c01 >> 5) & 0x3F, b01 = c01 & 0x1F;
      uint32_t r11 = (c11 >> 11) & 0x1F, g11 = (c11 >> 5) & 0x3F, b11 = c11 & 0x1F;
      // Bilinear weights in 16.16 domain
      uint32_t w00 = (uint32_t)(((uint64_t)wx0 * wy0) >> 16);
      uint32_t w10 = (uint32_t)(((uint64_t)wx1 * wy0) >> 16);
      uint32_t w01 = (uint32_t)(((uint64_t)wx0 * wy1) >> 16);
      uint32_t w11 = (uint32_t)(((uint64_t)wx1 * wy1) >> 16);
      // Weighted sum + rounding
      uint32_t r = (r00 * w00 + r10 * w10 + r01 * w01 + r11 * w11 + 32768) >> 16;
      uint32_t g = (g00 * w00 + g10 * w10 + g01 * w01 + g11 * w11 + 32768) >> 16;
      uint32_t b = (b00 * w00 + b10 * w10 + b01 * w01 + b11 * w11 + 32768) >> 16;
      if (r > 31) r = 31;
      if (g > 63) g = 63;
      if (b > 31) b = 31;
      out[y * dstW + x] = (uint16_t)((r << 11) | (g << 5) | b);
    }
  }
  return out;
}

void displayPattern(const uint16_t* imageData)
{
  M5.Display.clear();
  M5.Display.pushImage(7, 7, 160, 120, (const lgfx::rgb565_t *)ScaleImage50Percent(imageData));
  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", 180, 30);

  _rcaOutput.clear();
  if (_isPalMode) 
  {
    _rcaOutput.pushImage(0, 0, 384, 288, (const lgfx::rgb565_t *)ScaleImageForPalBilinear(imageData));
  } 
  else 
  {
    _rcaOutput.pushImage(0, 0, 320, 240, (const lgfx::rgb565_t *)imageData);
  }
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

  displayPattern(colour_bars_bmp);
}

void loop() {
  toggleVideoModeIfButtonPressed();
  checkPatternButton();

  delay(100);  
}
