#pragma once

#include <stdint.h>

class ImageScaler {
public:
  static constexpr int SourceWidth = 320;
  static constexpr int SourceHeight = 240;
  static constexpr int PreviewWidth = 160;
  static constexpr int PreviewHeight = 120;
  static constexpr int PalWidth = 384;
  static constexpr int PalHeight = 288;

  struct SourceRowPair {
    int lower;
    int upper;
  };

  // Pure, allocation-free row operations used by the scanline renderer.
  static void ScalePreviewRow(
      const uint16_t sourceRow[SourceWidth],
      uint16_t destinationRow[PreviewWidth]);
  static SourceRowPair GetPalSourceRows(int destinationRowIndex);
  static void ScalePalRowBilinear(
      const uint16_t topSourceRow[SourceWidth],
      const uint16_t bottomSourceRow[SourceWidth],
      int destinationRowIndex,
      uint16_t destinationRow[PalWidth]);
};
