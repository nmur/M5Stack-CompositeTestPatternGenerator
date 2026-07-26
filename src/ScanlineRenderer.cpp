#include "ScanlineRenderer.h"

namespace {

bool IsValid(
    const ScanlineRenderer::RowProvider& provider,
    const ScanlineRenderer::RowSink& sink) {
  return provider.decodeRow != nullptr && sink.writeRow != nullptr;
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

int FindCachedRow(const int cachedRows[2], int sourceRowIndex) {
  if (cachedRows[0] == sourceRowIndex) {
    return 0;
  }
  if (cachedRows[1] == sourceRowIndex) {
    return 1;
  }
  return -1;
}

}  // namespace

bool ScanlineRenderer::RenderNtsc(
    const RowProvider& provider,
    const RowSink& sink,
    Scratch& scratch) {
  if (!IsValid(provider, sink)) {
    return false;
  }

  bool succeeded = true;
  StartWrite(sink);
  for (int destinationRowIndex = 0;
       destinationRowIndex < ImageScaler::SourceHeight;
       ++destinationRowIndex) {
    if (!provider.decodeRow(
            provider.context,
            destinationRowIndex,
            scratch.sourceRows[0])
        || !sink.writeRow(
            sink.context,
            destinationRowIndex,
            scratch.sourceRows[0],
            ImageScaler::SourceWidth)) {
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
    const int sourceRowIndex = destinationRowIndex * 2;
    if (!provider.decodeRow(
            provider.context,
            sourceRowIndex,
            scratch.sourceRows[0])) {
      succeeded = false;
      break;
    }

    ImageScaler::ScalePreviewRow(
        scratch.sourceRows[0],
        scratch.destinationRow);
    if (!sink.writeRow(
            sink.context,
            destinationRowIndex,
            scratch.destinationRow,
            ImageScaler::PreviewWidth)) {
      succeeded = false;
      break;
    }
  }
  EndWrite(sink);
  return succeeded;
}

bool ScanlineRenderer::RenderPal(
    const RowProvider& provider,
    const RowSink& sink,
    Scratch& scratch) {
  if (!IsValid(provider, sink)) {
    return false;
  }

  int cachedRows[2] = {-1, -1};
  bool succeeded = true;
  StartWrite(sink);
  for (int destinationRowIndex = 0;
       destinationRowIndex < ImageScaler::PalHeight;
       ++destinationRowIndex) {
    const ImageScaler::SourceRowPair sourceRows =
        ImageScaler::GetPalSourceRows(destinationRowIndex);

    int lowerSlot = FindCachedRow(cachedRows, sourceRows.lower);
    if (lowerSlot < 0) {
      // Preserve an already-decoded upper row if it is in the cache.
      lowerSlot = cachedRows[0] == sourceRows.upper ? 1 : 0;
      if (!provider.decodeRow(
              provider.context,
              sourceRows.lower,
              scratch.sourceRows[lowerSlot])) {
        succeeded = false;
        break;
      }
      cachedRows[lowerSlot] = sourceRows.lower;
    }

    int upperSlot = lowerSlot;
    if (sourceRows.upper != sourceRows.lower) {
      upperSlot = FindCachedRow(cachedRows, sourceRows.upper);
      if (upperSlot < 0) {
        upperSlot = 1 - lowerSlot;
        if (!provider.decodeRow(
                provider.context,
                sourceRows.upper,
                scratch.sourceRows[upperSlot])) {
          succeeded = false;
          break;
        }
        cachedRows[upperSlot] = sourceRows.upper;
      }
    }

    ImageScaler::ScalePalRowBilinear(
        scratch.sourceRows[lowerSlot],
        scratch.sourceRows[upperSlot],
        destinationRowIndex,
        scratch.destinationRow);
    if (!sink.writeRow(
            sink.context,
            destinationRowIndex,
            scratch.destinationRow,
            ImageScaler::PalWidth)) {
      succeeded = false;
      break;
    }
  }
  EndWrite(sink);
  return succeeded;
}
