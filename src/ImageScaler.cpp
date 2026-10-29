#include "ImageScaler.h"

void ImageScaler::ScalePreviewRow(
    const uint16_t* sourceRow,
    int sourceWidth,
    uint16_t destinationRow[PreviewWidth]) {
  for (int destinationColumnIndex = 0;
       destinationColumnIndex < PreviewWidth;
       ++destinationColumnIndex) {
    const int sourceColumnIndex =
        destinationColumnIndex * sourceWidth / PreviewWidth;
    destinationRow[destinationColumnIndex] = sourceRow[sourceColumnIndex];
  }
}
