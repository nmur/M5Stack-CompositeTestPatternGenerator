#pragma once

#include <stddef.h>
#include <stdint.h>

#include "generated/PatternAssets.h"

enum class PatternDecodeResult : uint8_t {
    Ok = 0,
    NullDestination,
    UnsupportedCodecVersion,
    InvalidDimensions,
    RowOutOfRange,
    DestinationTooSmall,
    InvalidMetadata,
    InvalidRowIndex,
    InvalidRowOffsets,
    TruncatedRow,
    InvalidPaletteIndex,
    InvalidRunLength,
    RowTooLong,
    RowTooShort,
    TrailingRowData,
    UnsupportedCodec,
};

PatternDecodeResult decodePatternRow(
    const PatternAssets::Asset& asset,
    uint16_t y,
    uint16_t* destination,
    size_t destinationPixels
);

const char* patternDecodeResultMessage(PatternDecodeResult result);
