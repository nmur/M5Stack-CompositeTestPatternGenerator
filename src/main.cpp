#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>
#include <Preferences.h>
#include <stdlib.h>

#include "ImageScaler.h"
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

uint16_t* getPreviewImage(const uint16_t* imageData);
void displayPreview(const uint16_t* imageData);
const uint16_t* getNtscRcaImage(const uint16_t* imageData);
uint16_t* getPalRcaImage(const uint16_t* imageData);
void displayNtscRca(const uint16_t* imageData);
void displayPalRca(const uint16_t* imageData);
void displayRca(const uint16_t* imageData);

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

uint16_t* getPreviewImage(const uint16_t* imageData)
{
  return ImageScaler::ScaleImage50Percent(imageData);
}

void displayPreview(const uint16_t* imageData)
{
  uint16_t* previewImage = getPreviewImage(imageData);

  M5.Display.clear();
  if (previewImage)
  {
    M5.Display.pushImage(7, 7, ImageScaler::PreviewWidth, ImageScaler::PreviewHeight, (const lgfx::rgb565_t *)previewImage);
  }
  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", 180, 30);

  free(previewImage);
}

const uint16_t* getNtscRcaImage(const uint16_t* imageData)
{
  return imageData;
}

uint16_t* getPalRcaImage(const uint16_t* imageData)
{
  return ImageScaler::ScaleImageForPalBilinear(imageData);
}

void displayNtscRca(const uint16_t* imageData)
{
  const uint16_t* ntscRcaImage = getNtscRcaImage(imageData);
  _rcaOutput.pushImage(0, 0, ImageScaler::SourceWidth, ImageScaler::SourceHeight, (const lgfx::rgb565_t *)ntscRcaImage);
}

void displayPalRca(const uint16_t* imageData)
{
  const uint16_t* palRcaImage = getPalRcaImage(imageData);
  _rcaOutput.pushImage(0, 0, ImageScaler::PalWidth, ImageScaler::PalHeight, (const lgfx::rgb565_t *)palRcaImage);
}

void displayRca(const uint16_t* imageData)
{
  _rcaOutput.clear();

  if (_isPalMode)
  {
    displayPalRca(imageData);
  }
  else
  {
    displayNtscRca(imageData);
  }
}

void displayPattern(const uint16_t* imageData)
{
  displayPreview(imageData);
  displayRca(imageData);
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
