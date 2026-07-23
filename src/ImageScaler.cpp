#include "ImageScaler.h"

namespace {

struct BilinearCoordinate {
  int lowerIndex;
  int upperIndex;
  uint32_t lowerWeight;
  uint32_t upperWeight;
};

struct Rgb565Channels {
  uint32_t red;
  uint32_t green;
  uint32_t blue;
};

struct BilinearNeighborPixels {
  uint16_t topLeft;
  uint16_t topRight;
  uint16_t bottomLeft;
  uint16_t bottomRight;
};

uint32_t ComputeFixedPointScale(int sourceSize, int destinationSize) {
  return ((uint32_t)(sourceSize - 1) << 16) / (destinationSize - 1);
}

BilinearCoordinate ComputeBilinearCoordinate(int destinationIndex, uint32_t fixedPointScale, int sourceSize) {
  uint32_t fixedPointPosition = destinationIndex * fixedPointScale;

  int lowerIndex = fixedPointPosition >> 16;
  int upperIndex = (lowerIndex < sourceSize - 1) ? (lowerIndex + 1) : lowerIndex;

  uint32_t upperWeight = fixedPointPosition & 0xFFFF;
  uint32_t lowerWeight = 65536 - upperWeight;

  return {lowerIndex, upperIndex, lowerWeight, upperWeight};
}

BilinearNeighborPixels ReadBilinearNeighborPixels(
    const uint16_t* topSourceRow,
    const uint16_t* bottomSourceRow,
    const BilinearCoordinate& horizontalCoordinate) {
  return {
      topSourceRow[horizontalCoordinate.lowerIndex],
      topSourceRow[horizontalCoordinate.upperIndex],
      bottomSourceRow[horizontalCoordinate.lowerIndex],
      bottomSourceRow[horizontalCoordinate.upperIndex],
  };
}

Rgb565Channels ExpandRgb565Channels(uint16_t rgb565Pixel) {
  return {
      (uint32_t)((rgb565Pixel >> 11) & 0x1F),
      (uint32_t)((rgb565Pixel >> 5) & 0x3F),
      (uint32_t)(rgb565Pixel & 0x1F),
  };
}

uint32_t ComputeCombinedWeight(uint32_t horizontalWeight, uint32_t verticalWeight) {
  return (uint32_t)(((uint64_t)horizontalWeight * verticalWeight) >> 16);
}

uint32_t BlendChannelValue(
    uint32_t topLeftValue,
    uint32_t topRightValue,
    uint32_t bottomLeftValue,
    uint32_t bottomRightValue,
    uint32_t topLeftWeight,
    uint32_t topRightWeight,
    uint32_t bottomLeftWeight,
    uint32_t bottomRightWeight) {
  return (topLeftValue * topLeftWeight + topRightValue * topRightWeight +
          bottomLeftValue * bottomLeftWeight + bottomRightValue * bottomRightWeight + 32768) >>
         16;
}

uint16_t PackRgb565Pixel(uint32_t redValue, uint32_t greenValue, uint32_t blueValue) {
  if (redValue > 31) {
    redValue = 31;
  }
  if (greenValue > 63) {
    greenValue = 63;
  }
  if (blueValue > 31) {
    blueValue = 31;
  }

  return (uint16_t)((redValue << 11) | (greenValue << 5) | blueValue);
}

uint16_t ComputeBilinearScaledPixel(
    const uint16_t* topSourceRow,
    const uint16_t* bottomSourceRow,
    const BilinearCoordinate& verticalCoordinate,
    const BilinearCoordinate& horizontalCoordinate) {
  BilinearNeighborPixels neighborPixels =
      ReadBilinearNeighborPixels(
          topSourceRow,
          bottomSourceRow,
          horizontalCoordinate);

  Rgb565Channels topLeftChannels = ExpandRgb565Channels(neighborPixels.topLeft);
  Rgb565Channels topRightChannels = ExpandRgb565Channels(neighborPixels.topRight);
  Rgb565Channels bottomLeftChannels = ExpandRgb565Channels(neighborPixels.bottomLeft);
  Rgb565Channels bottomRightChannels = ExpandRgb565Channels(neighborPixels.bottomRight);

  uint32_t topLeftWeight = ComputeCombinedWeight(horizontalCoordinate.lowerWeight, verticalCoordinate.lowerWeight);
  uint32_t topRightWeight = ComputeCombinedWeight(horizontalCoordinate.upperWeight, verticalCoordinate.lowerWeight);
  uint32_t bottomLeftWeight = ComputeCombinedWeight(horizontalCoordinate.lowerWeight, verticalCoordinate.upperWeight);
  uint32_t bottomRightWeight = ComputeCombinedWeight(horizontalCoordinate.upperWeight, verticalCoordinate.upperWeight);

  uint32_t blendedRedValue = BlendChannelValue(
      topLeftChannels.red,
      topRightChannels.red,
      bottomLeftChannels.red,
      bottomRightChannels.red,
      topLeftWeight,
      topRightWeight,
      bottomLeftWeight,
      bottomRightWeight);

  uint32_t blendedGreenValue = BlendChannelValue(
      topLeftChannels.green,
      topRightChannels.green,
      bottomLeftChannels.green,
      bottomRightChannels.green,
      topLeftWeight,
      topRightWeight,
      bottomLeftWeight,
      bottomRightWeight);

  uint32_t blendedBlueValue = BlendChannelValue(
      topLeftChannels.blue,
      topRightChannels.blue,
      bottomLeftChannels.blue,
      bottomRightChannels.blue,
      topLeftWeight,
      topRightWeight,
      bottomLeftWeight,
      bottomRightWeight);

  return PackRgb565Pixel(blendedRedValue, blendedGreenValue, blendedBlueValue);
}

} 

void ImageScaler::ScalePreviewRow(
    const uint16_t sourceRow[SourceWidth],
    uint16_t destinationRow[PreviewWidth]) {
  for (int destinationColumnIndex = 0;
       destinationColumnIndex < PreviewWidth;
       ++destinationColumnIndex) {
    destinationRow[destinationColumnIndex] =
        sourceRow[destinationColumnIndex * 2];
  }
}

ImageScaler::SourceRowPair ImageScaler::GetPalSourceRows(
    int destinationRowIndex) {
  const uint32_t verticalScaleFactor =
      ComputeFixedPointScale(SourceHeight, PalHeight);
  const BilinearCoordinate verticalCoordinate =
      ComputeBilinearCoordinate(
          destinationRowIndex,
          verticalScaleFactor,
          SourceHeight);
  return {verticalCoordinate.lowerIndex, verticalCoordinate.upperIndex};
}

void ImageScaler::ScalePalRowBilinear(
    const uint16_t topSourceRow[SourceWidth],
    const uint16_t bottomSourceRow[SourceWidth],
    int destinationRowIndex,
    uint16_t destinationRow[PalWidth]) {
  const uint32_t horizontalScaleFactor =
      ComputeFixedPointScale(SourceWidth, PalWidth);
  const uint32_t verticalScaleFactor =
      ComputeFixedPointScale(SourceHeight, PalHeight);
  const BilinearCoordinate verticalCoordinate =
      ComputeBilinearCoordinate(
          destinationRowIndex,
          verticalScaleFactor,
          SourceHeight);

  for (int destinationColumnIndex = 0;
       destinationColumnIndex < PalWidth;
       ++destinationColumnIndex) {
    const BilinearCoordinate horizontalCoordinate =
        ComputeBilinearCoordinate(
            destinationColumnIndex,
            horizontalScaleFactor,
            SourceWidth);
    destinationRow[destinationColumnIndex] =
        ComputeBilinearScaledPixel(
            topSourceRow,
            bottomSourceRow,
            verticalCoordinate,
            horizontalCoordinate);
  }
}
