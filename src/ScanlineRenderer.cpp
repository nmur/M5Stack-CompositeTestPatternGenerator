#include "ScanlineRenderer.h"

namespace {

bool IsValid(
    const ScanlineRenderer::RowProvider& provider,
    const ScanlineRenderer::RowSink& sink) {
  return provider.decodeRow != nullptr && sink.writeRow != nullptr
      && provider.width > 0 && provider.width <= ImageScaler::MaxWidth
      && provider.height > 0 && provider.height <= ImageScaler::MaxHeight;
}

void StartWrite(const ScanlineRenderer::RowSink& sink) {
  if (sink.startWrite != nullptr) {
    sink.startWrite(sink.context);
  }
}

void EndWrite(const ScanlineRenderer::RowSink& sink) {
  if (sink.endWrite != nullptr) {
    sink.endWrite(sink.context);
  }
}

}  // namespace

bool ScanlineRenderer::RenderNative(
    const RowProvider& provider,
    const RowSink& sink,
    Scratch& scratch) {
  if (!IsValid(provider, sink)) {
    return false;
  }

  bool succeeded = true;
  StartWrite(sink);
  for (int destinationRowIndex = 0;
       destinationRowIndex < provider.height;
       ++destinationRowIndex) {
    if (!provider.decodeRow(
            provider.context,
            destinationRowIndex,
            scratch.sourceRow,
            ImageScaler::MaxWidth)
        || !sink.writeRow(
            sink.context,
            destinationRowIndex,
            scratch.sourceRow,
            provider.width)) {
      succeeded = false;
      break;
    }
  }
  EndWrite(sink);
  return succeeded;
}

bool ScanlineRenderer::RenderPreview(
    const RowProvider& provider,
    const RowSink& sink,
    Scratch& scratch) {
  if (!IsValid(provider, sink)) {
    return false;
  }

  bool succeeded = true;
  StartWrite(sink);
  for (int destinationRowIndex = 0;
       destinationRowIndex < ImageScaler::PreviewHeight;
       ++destinationRowIndex) {
    const int sourceRowIndex =
        destinationRowIndex * provider.height / ImageScaler::PreviewHeight;
    if (!provider.decodeRow(
            provider.context,
            sourceRowIndex,
            scratch.sourceRow,
            ImageScaler::MaxWidth)) {
      succeeded = false;
      break;
    }

    ImageScaler::ScalePreviewRow(
        scratch.sourceRow,
        provider.width,
        scratch.previewRow);
    if (!sink.writeRow(
            sink.context,
            destinationRowIndex,
            scratch.previewRow,
            ImageScaler::PreviewWidth)) {
      succeeded = false;
      break;
    }
  }
  EndWrite(sink);
  return succeeded;
}
