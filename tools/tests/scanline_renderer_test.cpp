#include <assert.h>
#include <stdio.h>

#include <vector>

#include "ScanlineRenderer.h"

namespace {

uint16_t PixelAt(int x, int y) {
  // Distinguish adjacent source rows and columns without an image fixture.
  return static_cast<uint16_t>(y * 401 + x);
}

struct Source {
  int width;
  int height;
  int failingRow;
  mutable std::vector<int> decodedRows;
};

bool DecodeRow(
    const void* context,
    int rowIndex,
    uint16_t* destination,
    size_t destinationPixels) {
  const Source& source = *static_cast<const Source*>(context);
  assert(rowIndex >= 0 && rowIndex < source.height);
  assert(destinationPixels == ImageScaler::MaxWidth);
  assert(destinationPixels >= static_cast<size_t>(source.width));
  source.decodedRows.push_back(rowIndex);
  if (rowIndex == source.failingRow) {
    return false;
  }
  for (int x = 0; x < source.width; ++x) {
    destination[x] = PixelAt(x, rowIndex);
  }
  return true;
}

struct Output {
  int sourceWidth;
  int sourceHeight;
  bool preview;
  int failingRow;
  int starts;
  int ends;
  int attemptedRows;
};

void StartWrite(void* context) {
  Output& output = *static_cast<Output*>(context);
  assert(output.starts == 0 && output.ends == 0);
  ++output.starts;
}

void EndWrite(void* context) {
  Output& output = *static_cast<Output*>(context);
  assert(output.starts == 1 && output.ends == 0);
  ++output.ends;
}

bool WriteRow(
    void* context,
    int destinationRow,
    const uint16_t* pixels,
    int count) {
  Output& output = *static_cast<Output*>(context);
  assert(output.starts == 1 && output.ends == 0);
  assert(destinationRow == output.attemptedRows);
  const int width = output.preview ? ImageScaler::PreviewWidth : output.sourceWidth;
  assert(count == width);
  for (int x = 0; x < count; ++x) {
    const int sourceX = output.preview
        ? x * output.sourceWidth / ImageScaler::PreviewWidth : x;
    const int sourceY = output.preview
        ? destinationRow * output.sourceHeight / ImageScaler::PreviewHeight
        : destinationRow;
    assert(pixels[x] == PixelAt(sourceX, sourceY));
  }
  ++output.attemptedRows;
  return destinationRow != output.failingRow;
}

ScanlineRenderer::RowProvider Provider(const Source& source) {
  return {&source, DecodeRow, source.width, source.height};
}

ScanlineRenderer::RowSink Sink(Output& output) {
  return {&output, StartWrite, WriteRow, EndWrite};
}

void TestSuccess(int width, int height, bool preview) {
  Source source = {width, height, -1, {}};
  Output output = {width, height, preview, -1, 0, 0, 0};
  ScanlineRenderer::Scratch scratch;
  const bool succeeded = preview
      ? ScanlineRenderer::RenderPreview(Provider(source), Sink(output), scratch)
      : ScanlineRenderer::RenderNative(Provider(source), Sink(output), scratch);
  assert(succeeded);
  assert(output.starts == 1 && output.ends == 1);
  const int rowCount = preview ? ImageScaler::PreviewHeight : height;
  assert(output.attemptedRows == rowCount);
  assert(source.decodedRows.size() == static_cast<size_t>(rowCount));
  for (int y = 0; y < rowCount; ++y) {
    assert(source.decodedRows[y] ==
        (preview ? y * height / ImageScaler::PreviewHeight : y));
  }
}

void TestRejectedProviders() {
  const int invalidDimensions[][2] = {
      {0, 240}, {-1, 240}, {ImageScaler::MaxWidth + 1, 240},
      {320, 0}, {320, -1}, {320, ImageScaler::MaxHeight + 1},
  };
  for (const auto& dimensions : invalidDimensions) {
    Source source = {dimensions[0], dimensions[1], -1, {}};
    Output output = {dimensions[0], dimensions[1], false, -1, 0, 0, 0};
    ScanlineRenderer::Scratch scratch;
    assert(!ScanlineRenderer::RenderNative(Provider(source), Sink(output), scratch));
    assert(!ScanlineRenderer::RenderPreview(Provider(source), Sink(output), scratch));
    assert(output.starts == 0 && output.ends == 0 && output.attemptedRows == 0);
    assert(source.decodedRows.empty());
  }

  Source source = {320, 240, -1, {}};
  Output output = {320, 240, false, -1, 0, 0, 0};
  ScanlineRenderer::Scratch scratch;
  auto provider = Provider(source);
  provider.decodeRow = nullptr;
  assert(!ScanlineRenderer::RenderNative(provider, Sink(output), scratch));
  assert(!ScanlineRenderer::RenderPreview(provider, Sink(output), scratch));
  auto sink = Sink(output);
  sink.writeRow = nullptr;
  assert(!ScanlineRenderer::RenderNative(Provider(source), sink, scratch));
  assert(!ScanlineRenderer::RenderPreview(Provider(source), sink, scratch));
  assert(output.starts == 0 && output.ends == 0 && output.attemptedRows == 0);
  assert(source.decodedRows.empty());
}

void TestFailure(bool preview, bool decodeFailure) {
  Source source = {384, 288, decodeFailure ? 7 : -1, {}};
  Output output = {384, 288, preview, decodeFailure ? -1 : 3, 0, 0, 0};
  ScanlineRenderer::Scratch scratch;
  const bool succeeded = preview
      ? ScanlineRenderer::RenderPreview(Provider(source), Sink(output), scratch)
      : ScanlineRenderer::RenderNative(Provider(source), Sink(output), scratch);
  assert(!succeeded);
  assert(output.starts == 1 && output.ends == 1);
  const int decodedCount = decodeFailure ? (preview ? 4 : 8) : 4;
  assert(source.decodedRows.size() == static_cast<size_t>(decodedCount));
  assert(output.attemptedRows == decodedCount - (decodeFailure ? 1 : 0));
}

void TestOptionalTransactions() {
  Source source = {1, 1, -1, {}};
  Output output = {1, 1, false, -1, 1, 0, 0};
  ScanlineRenderer::Scratch scratch;
  const ScanlineRenderer::RowSink sink = {&output, nullptr, WriteRow, nullptr};
  assert(ScanlineRenderer::RenderNative(Provider(source), sink, scratch));
  assert(output.attemptedRows == 1 && output.ends == 0);
}

}  // namespace

int main() {
  for (bool preview : {false, true}) {
    TestSuccess(ImageScaler::NtscWidth, ImageScaler::NtscHeight, preview);
    TestSuccess(ImageScaler::PalWidth, ImageScaler::PalHeight, preview);
    TestSuccess(1, 1, preview);
    TestFailure(preview, true);
    TestFailure(preview, false);
  }
  TestRejectedProviders();
  TestOptionalTransactions();
  puts("Native scanline renderer and LCD preview checks passed.");
}
