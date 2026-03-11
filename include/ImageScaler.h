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

  static uint16_t* ScaleImage50Percent(const uint16_t* imageData);
  static uint16_t* ScaleImageForPalBilinear(const uint16_t* imageData);
};
