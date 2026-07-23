#include <stdio.h>
#include <string.h>

#include "ImageScaler.h"
#include "PatternDecoder.h"
#include "ScanlineRenderer.h"
#include "generated/PatternAssets.h"

namespace {

struct OutputContext {
  int nextRow;
  int expectedWidth;
};

bool decodeAssetRow(
    const void* context,
    int sourceRowIndex,
    uint16_t destination[ImageScaler::SourceWidth]) {
  if (context == nullptr
      || sourceRowIndex < 0
      || sourceRowIndex >= ImageScaler::SourceHeight) {
    return false;
  }

  const PatternAssets::Asset& asset =
      *static_cast<const PatternAssets::Asset*>(context);
  return decodePatternRow(
             asset,
             static_cast<uint16_t>(sourceRowIndex),
             destination,
             ImageScaler::SourceWidth)
      == PatternDecodeResult::Ok;
}

bool writeLittleEndianRow(
    void* context,
    int destinationRowIndex,
    const uint16_t* rowPixels,
    int pixelCount) {
  OutputContext* output = static_cast<OutputContext*>(context);
  if (output == nullptr
      || rowPixels == nullptr
      || destinationRowIndex != output->nextRow
      || pixelCount != output->expectedWidth) {
    return false;
  }

  for (int pixelIndex = 0; pixelIndex < pixelCount; ++pixelIndex) {
    const uint16_t pixel = rowPixels[pixelIndex];
    if (fputc(pixel & 0xFF, stdout) == EOF
        || fputc(pixel >> 8, stdout) == EOF) {
      return false;
    }
  }
  ++output->nextRow;
  return true;
}

const PatternAssets::Asset* findAsset(const char* name) {
  for (size_t index = 0; index < PatternAssets::kCount; ++index) {
    if (strcmp(name, PatternAssets::kNames[index]) == 0) {
      return PatternAssets::kAll[index];
    }
  }
  return nullptr;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s PATTERN OUTPUT\n", argv[0]);
    return 2;
  }

  const PatternAssets::Asset* asset = findAsset(argv[1]);
  if (asset == nullptr) {
    fprintf(stderr, "unknown pattern: %s\n", argv[1]);
    return 2;
  }

  ScanlineRenderer::Scratch scratch = {};
  const ScanlineRenderer::RowProvider provider = {
    asset,
    decodeAssetRow,
  };
  OutputContext output = {0, 0};
  const ScanlineRenderer::RowSink sink = {
    &output,
    nullptr,
    writeLittleEndianRow,
    nullptr,
  };

  bool rendered = false;
  int expectedRows = 0;
  if (strcmp(argv[2], "ntsc_320x240") == 0) {
    output.expectedWidth = ImageScaler::SourceWidth;
    expectedRows = ImageScaler::SourceHeight;
    rendered = ScanlineRenderer::RenderNtsc(provider, sink, scratch);
  } else if (strcmp(argv[2], "preview_160x120") == 0) {
    output.expectedWidth = ImageScaler::PreviewWidth;
    expectedRows = ImageScaler::PreviewHeight;
    rendered = ScanlineRenderer::RenderPreview(provider, sink, scratch);
  } else if (strcmp(argv[2], "pal_384x288") == 0) {
    output.expectedWidth = ImageScaler::PalWidth;
    expectedRows = ImageScaler::PalHeight;
    rendered = ScanlineRenderer::RenderPal(provider, sink, scratch);
  } else {
    fprintf(stderr, "unknown output: %s\n", argv[2]);
    return 2;
  }

  if (!rendered || output.nextRow != expectedRows || fflush(stdout) == EOF) {
    fprintf(stderr, "render failed: %s %s\n", argv[1], argv[2]);
    return 1;
  }
  return 0;
}
