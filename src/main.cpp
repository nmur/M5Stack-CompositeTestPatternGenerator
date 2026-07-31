#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>
#include <Preferences.h>
#include <esp_heap_caps.h>

#include "ImageScaler.h"
#include "PatternDecoder.h"
#include "ScanlineRenderer.h"
#include "generated/PatternAssets.h"

Preferences _preferences;

const int VIDEO_MODE_BUTTON_PIN = 39; // Button B
const int PATTERN_BUTTON_PIN = 37; // Button A
const bool DEFAULT_IS_PAL_MODE = true;
const uint32_t PATTERN_BUTTON_DEBOUNCE_MS = 30;
const uint32_t PATTERN_BUTTON_LONG_PRESS_MS = 750;
const int STATIC_PATTERN_COUNT = 8;

bool _videoModeLastButtonState = HIGH;     
bool _patternButtonLastRawState = HIGH;
bool _patternButtonStableState = HIGH;
bool _patternButtonLongPressHandled = false;
uint32_t _patternButtonLastRawChangeMs = 0;
uint32_t _patternButtonPressedMs = 0;
bool _isPalMode = false;
bool _isRcaOutputReady = false;

static_assert(
  PatternAssets::kCount == STATIC_PATTERN_COUNT + 1,
  "Eight static patterns and the scrolling grid must be enabled");

enum class ScrollDirection : uint8_t
{
  Vertical,
  Horizontal,
};

ScanlineRenderer::Scratch _renderScratch;
int _currentPatternIndex = 0;

lgfx::rgb565_t _scrollWrapPixels[ImageScaler::PalWidth];
bool _isScrollingMode = false;
bool _isScrollingGridReady = false;
ScrollDirection _scrollDirection = ScrollDirection::Vertical;
int32_t _lastRcaScanLine = -1;

M5UnitRCA _rcaOutput;

M5UnitRCA GetPalRcaConfig();
M5UnitRCA GetNtscRcaConfig();

void displayError(const char* message);
void reportError(const char* message);

void initLcdDisplay();
bool initRcaOutput();
void loadVideoModeState();
void setRcaOutputVideoMode();

void restart();
void toggleVideoModeIfButtonPressed();
void toggleVideoMode();
void saveIsPalState(bool isPalMode);

bool decodeAssetRow(
  const void* context,
  int sourceRowIndex,
  uint16_t destination[ImageScaler::SourceWidth]);
void startPreviewWrite(void* context);
bool writePreviewRow(
  void* context,
  int destinationRowIndex,
  const uint16_t* rowPixels,
  int pixelCount);
void endPreviewWrite(void* context);
void startRcaWrite(void* context);
bool writeRcaRow(
  void* context,
  int destinationRowIndex,
  const uint16_t* rowPixels,
  int pixelCount);
void endRcaWrite(void* context);

bool displayPreview(const PatternAssets::Asset& asset);
bool displayRca(const PatternAssets::Asset& asset);
void displayPattern(const PatternAssets::Asset& asset);
void startScrollingGrid();
void stopScrollingGrid();
void toggleScrollingGrid();
void toggleScrollDirection();
void scrollGridOneRefresh();
void updateScrollingGrid();
void cyclePattern();
void handlePatternShortPress();
void checkPatternButton();

M5UnitRCA GetPalRcaConfig()
{
  return M5UnitRCA(384, 288,
                   384, 288,
                   M5UnitRCA::signal_type_t::PAL, 
                   M5UnitRCA::use_psram_t::psram_no_use,
                   26, 
                   128);
}

M5UnitRCA GetNtscRcaConfig()
{
  return M5UnitRCA(320, 240,
                   320, 240,
                   M5UnitRCA::signal_type_t::NTSC, 
                   M5UnitRCA::use_psram_t::psram_no_use,
                   26, 
                   128);
}

void displayError(const char* message)
{
  M5.Display.fillRect(0, 99, M5.Display.width(), 36, TFT_BLACK);
  M5.Display.setTextSize(1);
  M5.Display.setTextColor(TFT_RED, TFT_BLACK);
  M5.Display.drawString("ERROR", 2, 101);
  M5.Display.drawString(message, 2, 114);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.setTextSize(2);
}

void reportError(const char* message)
{
  displayError(message);
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
  _isPalMode = _preferences.getBool("isPal", DEFAULT_IS_PAL_MODE);
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

bool initRcaOutput()
{
  loadVideoModeState();
  setRcaOutputVideoMode();

  const int expectedWidth =
    _isPalMode ? ImageScaler::PalWidth : ImageScaler::SourceWidth;
  const int expectedHeight =
    _isPalMode ? ImageScaler::PalHeight : ImageScaler::SourceHeight;
  const size_t expectedFramebufferBytes =
    static_cast<size_t>(expectedWidth) * expectedHeight * sizeof(uint16_t);
  const size_t freeDmaBefore =
    heap_caps_get_free_size(MALLOC_CAP_DMA);

  const bool initSucceeded = _rcaOutput.init();

  if (!initSucceeded)
  {
    reportError("RCA initialization failed");
    return false;
  }

  // M5UnitRCA first creates an RGB332 framebuffer. Changing its depth
  // recreates the framebuffer as RGB565, but the library does not return the
  // second allocation result. Check the resulting internal-RAM consumption
  // before rendering so a failed recreation cannot be used.
  _rcaOutput.setColorDepth(m5gfx::color_depth_t::rgb565_nonswapped);

  const size_t freeDmaAfter =
    heap_caps_get_free_size(MALLOC_CAP_DMA);
  const size_t observedDmaAllocation =
    freeDmaBefore >= freeDmaAfter ? freeDmaBefore - freeDmaAfter : 0;
  const int colorDepthBits =
    static_cast<int>(_rcaOutput.getColorDepth())
    & static_cast<int>(m5gfx::color_depth_t::bit_mask);
  const bool dimensionsMatch =
    _rcaOutput.width() == expectedWidth
    && _rcaOutput.height() == expectedHeight;
  const bool colorDepthMatches = colorDepthBits == 16;
  const bool framebufferAllocationObserved =
    observedDmaAllocation >= expectedFramebufferBytes;

  if (!dimensionsMatch
      || !colorDepthMatches
      || !framebufferAllocationObserved)
  {
    reportError("RCA framebuffer failed");
    return false;
  }

  return true;
}

bool decodeAssetRow(
  const void* context,
  int sourceRowIndex,
  uint16_t destination[ImageScaler::SourceWidth])
{
  if (context == nullptr
      || sourceRowIndex < 0
      || sourceRowIndex >= ImageScaler::SourceHeight)
  {
    return false;
  }

  const PatternAssets::Asset& asset =
    *static_cast<const PatternAssets::Asset*>(context);
  if (asset.width != ImageScaler::SourceWidth
      || asset.height != ImageScaler::SourceHeight)
  {
    return false;
  }

  return decodePatternRow(
      asset,
      static_cast<uint16_t>(sourceRowIndex),
      destination,
      ImageScaler::SourceWidth)
    == PatternDecodeResult::Ok;
}

void startPreviewWrite(void*)
{
  M5.Display.startWrite();
}

bool writePreviewRow(
  void*,
  int destinationRowIndex,
  const uint16_t* rowPixels,
  int pixelCount)
{
  if (rowPixels == nullptr
      || destinationRowIndex < 0
      || destinationRowIndex >= ImageScaler::PreviewHeight
      || pixelCount != ImageScaler::PreviewWidth)
  {
    return false;
  }

  M5.Display.pushImage(
    7,
    7 + destinationRowIndex,
    ImageScaler::PreviewWidth,
    1,
    reinterpret_cast<const lgfx::rgb565_t*>(rowPixels));
  return true;
}

void endPreviewWrite(void*)
{
  M5.Display.endWrite();
}

void startRcaWrite(void*)
{
  _rcaOutput.startWrite();
}

bool writeRcaRow(
  void*,
  int destinationRowIndex,
  const uint16_t* rowPixels,
  int pixelCount)
{
  const int expectedWidth =
    _isPalMode ? ImageScaler::PalWidth : ImageScaler::SourceWidth;
  const int expectedHeight =
    _isPalMode ? ImageScaler::PalHeight : ImageScaler::SourceHeight;
  if (rowPixels == nullptr
      || destinationRowIndex < 0
      || destinationRowIndex >= expectedHeight
      || pixelCount != expectedWidth)
  {
    return false;
  }

  _rcaOutput.pushImage(
    0,
    destinationRowIndex,
    expectedWidth,
    1,
    reinterpret_cast<const lgfx::rgb565_t*>(rowPixels));
  return true;
}

void endRcaWrite(void*)
{
  _rcaOutput.endWrite();
}

bool displayPreview(const PatternAssets::Asset& asset)
{
  const ScanlineRenderer::RowProvider provider = {
    &asset,
    decodeAssetRow,
  };
  const ScanlineRenderer::RowSink sink = {
    nullptr,
    startPreviewWrite,
    writePreviewRow,
    endPreviewWrite,
  };

  M5.Display.clear();
  const bool rendered =
    ScanlineRenderer::RenderPreview(provider, sink, _renderScratch);

  if (!rendered)
  {
    reportError("Preview rendering failed");
    return false;
  }

  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", 180, 30);
  return true;
}

bool displayRca(const PatternAssets::Asset& asset)
{
  if (!_isRcaOutputReady)
  {
    reportError("RCA output unavailable");
    return false;
  }

  const ScanlineRenderer::RowProvider provider = {
    &asset,
    decodeAssetRow,
  };
  const ScanlineRenderer::RowSink sink = {
    nullptr,
    startRcaWrite,
    writeRcaRow,
    endRcaWrite,
  };

  _rcaOutput.clear();
  const bool rendered = _isPalMode
    ? ScanlineRenderer::RenderPal(provider, sink, _renderScratch)
    : ScanlineRenderer::RenderNtsc(provider, sink, _renderScratch);

  if (!rendered)
  {
    reportError(_isPalMode
      ? "PAL rendering failed"
      : "NTSC rendering failed");
    return false;
  }
  return true;
}

void displayPattern(const PatternAssets::Asset& asset)
{
  displayPreview(asset);
  displayRca(asset);
}

void startScrollingGrid()
{
  _isScrollingMode = true;
  _scrollDirection = ScrollDirection::Vertical;
  displayPattern(PatternAssets::kScrollingGrid);
  if (!_isRcaOutputReady)
  {
    return;
  }

  _lastRcaScanLine = _rcaOutput.getScanLine();
  _isScrollingGridReady = _lastRcaScanLine >= 0;
  if (!_isScrollingGridReady)
  {
    reportError("RCA refresh sync unavailable");
  }
}

void stopScrollingGrid()
{
  _isScrollingMode = false;
  _isScrollingGridReady = false;
  displayPattern(*PatternAssets::kAll[_currentPatternIndex]);
}

void toggleScrollingGrid()
{
  if (_isScrollingMode)
  {
    stopScrollingGrid();
  }
  else
  {
    startScrollingGrid();
  }
}

void toggleScrollDirection()
{
  _scrollDirection = _scrollDirection == ScrollDirection::Vertical
    ? ScrollDirection::Horizontal
    : ScrollDirection::Vertical;
}

void scrollGridOneRefresh()
{
  const int width = _rcaOutput.width();
  const int height = _rcaOutput.height();
  if (_scrollDirection == ScrollDirection::Vertical)
  {
    // Capture the outgoing row so the image wraps without a seam.
    _rcaOutput.readRect(0, 0, width, 1, _scrollWrapPixels);
    _rcaOutput.scroll(0, -1);
    _rcaOutput.pushImage(0, height - 1, width, 1, _scrollWrapPixels);
  }
  else
  {
    // The PAL height (288) also fits in the 384-pixel wrap buffer.
    _rcaOutput.readRect(0, 0, 1, height, _scrollWrapPixels);
    _rcaOutput.scroll(-1, 0);
    _rcaOutput.pushImage(width - 1, 0, 1, height, _scrollWrapPixels);
  }
}

void updateScrollingGrid()
{
  if (!_isScrollingGridReady)
  {
    return;
  }

  const int32_t scanLine = _rcaOutput.getScanLine();
  if (scanLine < 0)
  {
    _isScrollingGridReady = false;
    reportError("RCA refresh sync lost");
    return;
  }

  // Panel_CVBS resets its scanline counter at every PAL or NTSC refresh.
  if (scanLine < _lastRcaScanLine)
  {
    scrollGridOneRefresh();
  }
  _lastRcaScanLine = scanLine;
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
  _currentPatternIndex =
    (_currentPatternIndex + 1) % STATIC_PATTERN_COUNT;
  displayPattern(*PatternAssets::kAll[_currentPatternIndex]);
}

void handlePatternShortPress()
{
  if (_isScrollingMode)
  {
    toggleScrollDirection();
  }
  else
  {
    cyclePattern();
  }
}

void checkPatternButton()
{
  const uint32_t now = millis();
  const bool rawState = digitalRead(PATTERN_BUTTON_PIN);

  if (rawState != _patternButtonLastRawState)
  {
    _patternButtonLastRawState = rawState;
    _patternButtonLastRawChangeMs = now;
  }

  if (now - _patternButtonLastRawChangeMs >= PATTERN_BUTTON_DEBOUNCE_MS
      && rawState != _patternButtonStableState)
  {
    _patternButtonStableState = rawState;
    if (rawState == LOW)
    {
      _patternButtonPressedMs = now;
      _patternButtonLongPressHandled = false;
    }
    else if (!_patternButtonLongPressHandled)
    {
      handlePatternShortPress();
    }
  }

  if (_patternButtonStableState == LOW
      && !_patternButtonLongPressHandled
      && now - _patternButtonPressedMs >= PATTERN_BUTTON_LONG_PRESS_MS)
  {
    _patternButtonLongPressHandled = true;
    toggleScrollingGrid();
  }
}

void setup() {
  pinMode(VIDEO_MODE_BUTTON_PIN, INPUT_PULLUP);
  pinMode(PATTERN_BUTTON_PIN, INPUT_PULLUP);

  initLcdDisplay();
  _isRcaOutputReady = initRcaOutput();

  displayPattern(*PatternAssets::kAll[0]);
}

void loop() {
  toggleVideoModeIfButtonPressed();
  checkPatternButton();
  updateScrollingGrid();
  delay(1);
}
