#include "PatternDecoder.h"

#include <algorithm>

namespace {

bool hasExpectedPayloadSize(const PatternAssets::Asset& asset) {
    if (asset.codec == PatternAssets::Codec::SolidRgb565) {
        return asset.payloadSize == sizeof(uint16_t);
    }

    const uint64_t expected =
        static_cast<uint64_t>(asset.paletteSize) * sizeof(uint16_t)
        + static_cast<uint64_t>(asset.uniqueRowCount + 1) * sizeof(uint16_t)
        + asset.rowDataSize
        + static_cast<uint64_t>(asset.height) * sizeof(uint8_t);
    return asset.payloadSize == expected;
}

}  // namespace

PatternDecodeResult decodePatternRow(
    const PatternAssets::Asset& asset,
    uint16_t y,
    uint16_t* destination,
    size_t destinationPixels
) {
    if (destination == nullptr) {
        return PatternDecodeResult::NullDestination;
    }
    if (asset.codecVersion != PatternAssets::kCodecVersion) {
        return PatternDecodeResult::UnsupportedCodecVersion;
    }
    if (asset.width == 0 || asset.height == 0) {
        return PatternDecodeResult::InvalidDimensions;
    }
    if (y >= asset.height) {
        return PatternDecodeResult::RowOutOfRange;
    }
    if (destinationPixels < asset.width) {
        return PatternDecodeResult::DestinationTooSmall;
    }
    if (
        asset.palette == nullptr
        || asset.paletteSize == 0
        || asset.paletteSize > 256
        || !hasExpectedPayloadSize(asset)
    ) {
        return PatternDecodeResult::InvalidMetadata;
    }

    if (asset.codec == PatternAssets::Codec::SolidRgb565) {
        if (
            asset.paletteSize != 1
            || asset.uniqueRowCount != 0
            || asset.rowDataSize != 0
            || asset.rowOffsets != nullptr
            || asset.rowData != nullptr
            || asset.rowMap != nullptr
        ) {
            return PatternDecodeResult::InvalidMetadata;
        }
        std::fill_n(destination, asset.width, asset.palette[0]);
        return PatternDecodeResult::Ok;
    }

    if (asset.codec != PatternAssets::Codec::PaletteRleRows) {
        return PatternDecodeResult::UnsupportedCodec;
    }
    if (
        asset.uniqueRowCount == 0
        || asset.uniqueRowCount > 256
        || asset.rowOffsets == nullptr
        || asset.rowData == nullptr
        || asset.rowMap == nullptr
        || asset.rowDataSize == 0
    ) {
        return PatternDecodeResult::InvalidMetadata;
    }
    if (
        asset.rowOffsets[0] != 0
        || asset.rowOffsets[asset.uniqueRowCount] != asset.rowDataSize
    ) {
        return PatternDecodeResult::InvalidRowOffsets;
    }

    const uint8_t uniqueRowIndex = asset.rowMap[y];
    if (uniqueRowIndex >= asset.uniqueRowCount) {
        return PatternDecodeResult::InvalidRowIndex;
    }
    uint32_t offset = asset.rowOffsets[uniqueRowIndex];
    const uint32_t end = asset.rowOffsets[uniqueRowIndex + 1];
    if (offset > end || end > asset.rowDataSize) {
        return PatternDecodeResult::InvalidRowOffsets;
    }

    size_t written = 0;
    while (offset < end) {
        if (written == asset.width) {
            return PatternDecodeResult::TrailingRowData;
        }
        const uint8_t paletteIndex = asset.rowData[offset++];
        if (paletteIndex >= asset.paletteSize) {
            return PatternDecodeResult::InvalidPaletteIndex;
        }

        uint32_t runLength = 0;
        uint8_t shift = 0;
        bool complete = false;
        for (uint8_t byteCount = 0; byteCount < 3; ++byteCount) {
            if (offset >= end) {
                return PatternDecodeResult::TruncatedRow;
            }
            const uint8_t byte = asset.rowData[offset++];
            runLength |= static_cast<uint32_t>(byte & 0x7F) << shift;
            if ((byte & 0x80) == 0) {
                complete = true;
                break;
            }
            shift += 7;
        }
        if (!complete || runLength == 0 || runLength > asset.width) {
            return PatternDecodeResult::InvalidRunLength;
        }
        if (written + runLength > asset.width) {
            return PatternDecodeResult::RowTooLong;
        }
        std::fill_n(destination + written, runLength, asset.palette[paletteIndex]);
        written += runLength;
    }

    return written == asset.width
        ? PatternDecodeResult::Ok
        : PatternDecodeResult::RowTooShort;
}

const char* patternDecodeResultMessage(PatternDecodeResult result) {
    switch (result) {
        case PatternDecodeResult::Ok:
            return "ok";
        case PatternDecodeResult::NullDestination:
            return "destination is null";
        case PatternDecodeResult::UnsupportedCodecVersion:
            return "unsupported codec version";
        case PatternDecodeResult::InvalidDimensions:
            return "invalid dimensions";
        case PatternDecodeResult::RowOutOfRange:
            return "row is out of range";
        case PatternDecodeResult::DestinationTooSmall:
            return "destination is too small";
        case PatternDecodeResult::InvalidMetadata:
            return "invalid asset metadata";
        case PatternDecodeResult::InvalidRowIndex:
            return "invalid unique-row index";
        case PatternDecodeResult::InvalidRowOffsets:
            return "invalid row offsets";
        case PatternDecodeResult::TruncatedRow:
            return "truncated encoded row";
        case PatternDecodeResult::InvalidPaletteIndex:
            return "invalid palette index";
        case PatternDecodeResult::InvalidRunLength:
            return "invalid run length";
        case PatternDecodeResult::RowTooLong:
            return "decoded row is too long";
        case PatternDecodeResult::RowTooShort:
            return "decoded row is too short";
        case PatternDecodeResult::TrailingRowData:
            return "encoded row has trailing data";
        case PatternDecodeResult::UnsupportedCodec:
            return "unsupported codec";
    }
    return "unknown decode result";
}
