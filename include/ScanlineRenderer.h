#pragma once

#include <stddef.h>
#include <stdint.h>

#include "ImageScaler.h"

// Allocation-free rendering from an arbitrary 320x240 RGB565 row source.
//
// A RowProvider may represent a raw image, a compressed asset, or a generated
// pattern. decodeRow must write exactly ImageScaler::SourceWidth pixels.
//
// A RowSink receives complete output rows. startWrite/endWrite are optional
// transaction hooks; endWrite is called after startWrite even if decoding or a
// transfer fails.
class ScanlineRenderer {
public:
  typedef bool (*DecodeRowCallback)(
      const void* context,
      int sourceRowIndex,
      uint16_t destination[ImageScaler::SourceWidth]);

  struct RowProvider {
    const void* context;
    DecodeRowCallback decodeRow;
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

  // PAL needs two decoded source rows and one completed destination row.
  // NTSC and preview reuse the same storage.
  struct Scratch {
    uint16_t sourceRows[2][ImageScaler::SourceWidth];
    uint16_t destinationRow[ImageScaler::PalWidth];
  };

  static constexpr size_t ScratchBytes = sizeof(Scratch);

  static RowProvider RawRgb565Provider(const uint16_t* imageData);

  static bool RenderNtsc(
      const RowProvider& provider,
      const RowSink& sink,
      Scratch& scratch);
  static bool RenderPreview(
      const RowProvider& provider,
      const RowSink& sink,
      Scratch& scratch);
  static bool RenderPal(
      const RowProvider& provider,
      const RowSink& sink,
      Scratch& scratch);

private:
  static bool DecodeRawRgb565Row(
      const void* context,
      int sourceRowIndex,
      uint16_t destination[ImageScaler::SourceWidth]);
};

static_assert(
    ScanlineRenderer::ScratchBytes <= 4096,
    "Scanline renderer scratch storage must remain at or below 4 KB");
