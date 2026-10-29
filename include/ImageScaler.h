#pragma once

#include <stdint.h>

// Only the LCD preview is resized. Composite output uses native image rows.
class ImageScaler {
public:
  static constexpr int NtscWidth = 320;
  static constexpr int NtscHeight = 240;
  static constexpr int PalWidth = 384;
  static constexpr int PalHeight = 288;
  static constexpr int MaxWidth = PalWidth;
  static constexpr int MaxHeight = PalHeight;
  static constexpr int PreviewWidth = 160;
  static constexpr int PreviewHeight = 120;

  // The caller supplies a valid source row of sourceWidth pixels.
  static void ScalePreviewRow(
      const uint16_t* sourceRow,
      int sourceWidth,
      uint16_t destinationRow[PreviewWidth]);
};
