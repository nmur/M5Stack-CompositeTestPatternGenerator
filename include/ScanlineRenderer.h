#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ImageScaler.h"

// Allocation-free rendering from a native PAL or NTSC RGB565 row source.
//
// A RowProvider may represent a raw image, a compressed asset, or a generated
// pattern. decodeRow writes provider.width pixels and receives the full buffer
// capacity in destinationPixels.
//
// A RowSink receives complete output rows. startWrite/endWrite are optional
// transaction hooks; endWrite is called after startWrite even if decoding or a
// transfer fails.
class ScanlineRenderer {
public:
  typedef bool (*DecodeRowCallback)(
      const void* context,
      int sourceRowIndex,
      uint16_t* destination,
      size_t destinationPixels);

  struct RowProvider {
    const void* context;
    DecodeRowCallback decodeRow;
    int width;
    int height;
  };

  typedef void (*WriteTransactionCallback)(void* context);
  typedef bool (*WriteRowCallback)(
      void* context,
      int destinationRowIndex,
      const uint16_t* rowPixels,
      int pixelCount);

  struct RowSink {
    void* context;
    WriteTransactionCallback startWrite;
    WriteRowCallback writeRow;
    WriteTransactionCallback endWrite;
  };

  struct Scratch {
    uint16_t sourceRow[ImageScaler::MaxWidth];
    uint16_t previewRow[ImageScaler::PreviewWidth];
  };

  static constexpr size_t ScratchBytes = sizeof(Scratch);

  static bool RenderNative(
      const RowProvider& provider,
      const RowSink& sink,
      Scratch& scratch);
  static bool RenderPreview(
      const RowProvider& provider,
      const RowSink& sink,
      Scratch& scratch);
};

static_assert(
    ScanlineRenderer::ScratchBytes <= 4096,
    "Scanline renderer scratch storage must remain at or below 4 KB");
