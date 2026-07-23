#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"
#include <M5ModuleRCA.h>
#include <M5UnitRCA.h>
#include <Preferences.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include <esp32-hal-psram.h>

#include "ImageScaler.h"
#include "PatternDecoder.h"
#include "ScanlineRenderer.h"
#include "generated/PatternAssets.h"

// Override only for diagnostics; persisted user preferences still take priority.
#ifndef DEFAULT_VIDEO_MODE_PAL
#define DEFAULT_VIDEO_MODE_PAL 1
#endif

#ifndef PATTERN_SELF_TEST_CYCLES
#define PATTERN_SELF_TEST_CYCLES 0
#endif

#if PATTERN_SELF_TEST_CYCLES < 0
#error "PATTERN_SELF_TEST_CYCLES must not be negative"
#endif

Preferences _preferences;

const int VIDEO_MODE_BUTTON_PIN = 39; // Button B
const int PATTERN_BUTTON_PIN = 37; // Button A
const bool DEFAULT_IS_PAL_MODE = DEFAULT_VIDEO_MODE_PAL != 0;

bool _videoModeLastButtonState = HIGH;     
bool _patternLastButtonState = HIGH;
bool _isPalMode = false;
bool _isRcaOutputReady = false;

static_assert(PatternAssets::kCount == 8, "All eight test patterns must be enabled");

ScanlineRenderer::Scratch _renderScratch;
int _currentPatternIndex = 0;

M5UnitRCA _rcaOutput;

M5UnitRCA GetPalRcaConfig();
M5UnitRCA GetNtscRcaConfig();

const char* getResetReasonName(esp_reset_reason_t reason);
const char* getBoardName(m5::board_t board);
void initDiagnostics();
void logBoardDiagnostics();
void logMemoryDiagnostics(const char* stage);
void displayError(const char* message);
void reportError(const char* message);
bool verifyRenderHeapUnchanged(size_t freeHeapBefore, const char* outputName);

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
void displayPattern(const PatternAssets::Asset& asset, const char* patternName);
void cyclePattern();
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

const char* getResetReasonName(esp_reset_reason_t reason)
{
  switch (reason)
  {
    case ESP_RST_POWERON:
      return "power-on";
    case ESP_RST_EXT:
      return "external";
    case ESP_RST_SW:
      return "software";
    case ESP_RST_PANIC:
      return "panic";
    case ESP_RST_INT_WDT:
      return "interrupt-watchdog";
    case ESP_RST_TASK_WDT:
      return "task-watchdog";
    case ESP_RST_WDT:
      return "watchdog";
    case ESP_RST_DEEPSLEEP:
      return "deep-sleep";
    case ESP_RST_BROWNOUT:
      return "brownout";
    case ESP_RST_SDIO:
      return "SDIO";
    case ESP_RST_UNKNOWN:
    default:
      return "unknown";
  }
}

const char* getBoardName(m5::board_t board)
{
  switch (board)
  {
    case m5::board_t::board_M5StickC:
      return "M5StickC";
    case m5::board_t::board_M5StickCPlus:
      // The Plus SE currently uses the Plus-compatible hardware profile.
      return "M5StickC Plus / Plus SE";
    case m5::board_t::board_M5StickCPlus2:
      return "M5StickC Plus2";
    case m5::board_t::board_unknown:
      return "unknown";
    default:
      return "other M5 board";
  }
}

void initDiagnostics()
{
  Serial.begin(115200);
  delay(50);

  const esp_reset_reason_t resetReason = esp_reset_reason();
  Serial.printf(
    "[diag] reset_reason=%s (%d)\n",
    getResetReasonName(resetReason),
    static_cast<int>(resetReason));
}

void logBoardDiagnostics()
{
  const m5::board_t board = M5.getBoard();
  Serial.printf(
    "[diag] detected_board=%s (%d)\n",
    getBoardName(board),
    static_cast<int>(board));
  Serial.printf("[diag] psramFound()=%s\n", psramFound() ? "true" : "false");
}

void logMemoryDiagnostics(const char* stage)
{
  const size_t freeInternalHeap =
    heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const size_t largest8BitBlock =
    heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  const size_t largestDmaBlock =
    heap_caps_get_largest_free_block(MALLOC_CAP_DMA);

  Serial.printf(
    "[diag] heap stage=%s free_internal=%lu largest_8bit=%lu largest_dma=%lu\n",
    stage,
    static_cast<unsigned long>(freeInternalHeap),
    static_cast<unsigned long>(largest8BitBlock),
    static_cast<unsigned long>(largestDmaBlock));
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
  Serial.printf("[error] %s\n", message);
  logMemoryDiagnostics("error");
  displayError(message);
}

bool verifyRenderHeapUnchanged(size_t freeHeapBefore, const char* outputName)
{
  const size_t freeHeapAfter =
    heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const bool unchanged = freeHeapBefore == freeHeapAfter;

  Serial.printf(
    "[diag] render_heap output=%s before=%lu after=%lu result=%s\n",
    outputName,
    static_cast<unsigned long>(freeHeapBefore),
    static_cast<unsigned long>(freeHeapAfter),
    unchanged ? "stable" : "changed");

  if (!unchanged)
  {
    reportError("Renderer heap changed");
  }
  return unchanged;
}

void initLcdDisplay()
{
  M5.begin();
  M5.Display.setTextSize(2);
  M5.Display.setRotation(1);
  M5.Display.clear();

  // M5GFX retains a small bookkeeping allocation on its first typed image
  // transfer. Perform that one-time initialization before per-pattern heap
  // invariants are measured.
  M5.Display.startWrite();
  M5.Display.pushImage(
    7,
    7,
    ImageScaler::PreviewWidth,
    1,
    reinterpret_cast<const lgfx::rgb565_t*>(
      _renderScratch.destinationRow));
  M5.Display.endWrite();
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

  Serial.printf(
    "[diag] RCA setup mode=%s size=%dx%d psram=disabled\n",
    _isPalMode ? "PAL" : "NTSC",
    expectedWidth,
    expectedHeight);

  _rcaOutput.setOutputBoost(true);
  const bool initSucceeded = _rcaOutput.init();
  Serial.printf(
    "[diag] RCA init result=%s\n",
    initSucceeded ? "success" : "failure");

  if (!initSucceeded)
  {
    reportError("RCA initialization failed");
    return false;
  }

  // M5UnitRCA initially creates an RGB332 framebuffer. Changing depth
  // recreates it as RGB565, but the library API does not return the result
  // of that second initialization. Validate every observable property and
  // the expected internal-RAM consumption before allowing rendering.
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

  Serial.printf(
    "[diag] RCA framebuffer expected=%lu observed_dma=%lu depth=%d "
    "actual=%dx%d result=%s\n",
    static_cast<unsigned long>(expectedFramebufferBytes),
    static_cast<unsigned long>(observedDmaAllocation),
    colorDepthBits,
    _rcaOutput.width(),
    _rcaOutput.height(),
    dimensionsMatch
      && colorDepthMatches
      && framebufferAllocationObserved
        ? "success"
        : "failure");

  if (!dimensionsMatch
      || !colorDepthMatches
      || !framebufferAllocationObserved)
  {
    reportError("RCA framebuffer failed");
    return false;
  }

  logMemoryDiagnostics("after RCA init");
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
    Serial.printf(
      "[error] Pattern row request is invalid: row=%d\n",
      sourceRowIndex);
    return false;
  }

  const PatternAssets::Asset& asset =
    *static_cast<const PatternAssets::Asset*>(context);
  if (asset.width != ImageScaler::SourceWidth
      || asset.height != ImageScaler::SourceHeight)
  {
    Serial.printf(
      "[error] Pattern dimensions are invalid: actual=%ux%u expected=%dx%d\n",
      static_cast<unsigned int>(asset.width),
      static_cast<unsigned int>(asset.height),
      ImageScaler::SourceWidth,
      ImageScaler::SourceHeight);
    return false;
  }

  const PatternDecodeResult result = decodePatternRow(
    asset,
    static_cast<uint16_t>(sourceRowIndex),
    destination,
    ImageScaler::SourceWidth);
  if (result != PatternDecodeResult::Ok)
  {
    Serial.printf(
      "[error] Pattern decode failed: row=%d result=%s\n",
      sourceRowIndex,
      patternDecodeResultMessage(result));
    return false;
  }
  return true;
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
  const size_t freeHeapBefore =
    heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const bool rendered =
    ScanlineRenderer::RenderPreview(provider, sink, _renderScratch);
  const bool heapUnchanged =
    verifyRenderHeapUnchanged(freeHeapBefore, "preview");

  if (!rendered)
  {
    reportError("Preview rendering failed");
    return false;
  }

  M5.Display.drawString(_isPalMode ? "PAL" : "NTSC", 180, 30);
  if (!heapUnchanged)
  {
    return false;
  }
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
  const size_t freeHeapBefore =
    heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  const bool rendered = _isPalMode
    ? ScanlineRenderer::RenderPal(provider, sink, _renderScratch)
    : ScanlineRenderer::RenderNtsc(provider, sink, _renderScratch);
  const bool heapUnchanged = verifyRenderHeapUnchanged(
    freeHeapBefore,
    _isPalMode ? "PAL" : "NTSC");

  if (!rendered)
  {
    reportError(_isPalMode
      ? "PAL rendering failed"
      : "NTSC rendering failed");
    return false;
  }
  return heapUnchanged;
}

void displayPattern(
  const PatternAssets::Asset& asset,
  const char* patternName)
{
  Serial.printf(
    "[diag] pattern name=%s payload=%lu decoded_crc32=%08lx\n",
    patternName,
    static_cast<unsigned long>(asset.payloadSize),
    static_cast<unsigned long>(asset.decodedCrc32));

  const bool previewRendered = displayPreview(asset);
  const bool rcaRendered = displayRca(asset);
  Serial.printf(
    "[diag] pattern result=%s preview=%s rca=%s\n",
    patternName,
    previewRendered ? "success" : "failure",
    rcaRendered ? "success" : "failure");
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
    (_currentPatternIndex + 1) % PatternAssets::kCount;
  displayPattern(
    *PatternAssets::kAll[_currentPatternIndex],
    PatternAssets::kNames[_currentPatternIndex]);
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
  initDiagnostics();

  pinMode(VIDEO_MODE_BUTTON_PIN, INPUT_PULLUP);
  pinMode(PATTERN_BUTTON_PIN, INPUT_PULLUP);

  initLcdDisplay();
  logBoardDiagnostics();
  logMemoryDiagnostics("before RCA init");
  _isRcaOutputReady = initRcaOutput();

  displayPattern(*PatternAssets::kAll[0], PatternAssets::kNames[0]);

#if PATTERN_SELF_TEST_CYCLES > 0
  Serial.printf(
    "[diag] pattern self-test begin cycles=%d patterns=%u\n",
    PATTERN_SELF_TEST_CYCLES,
    static_cast<unsigned int>(PatternAssets::kCount));
  for (int cycleIndex = 0;
       cycleIndex < PATTERN_SELF_TEST_CYCLES;
       ++cycleIndex)
  {
    for (size_t patternIndex = 0;
         patternIndex < PatternAssets::kCount;
         ++patternIndex)
    {
      displayPattern(
        *PatternAssets::kAll[patternIndex],
        PatternAssets::kNames[patternIndex]);
    }
  }
  logMemoryDiagnostics("after pattern self-test");
  Serial.println("[diag] pattern self-test complete");
#endif
}

void loop() {
  toggleVideoModeIfButtonPressed();
  checkPatternButton();

  delay(100);  
}
