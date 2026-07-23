#include <stdint.h>

#include <array>
#include <iostream>
#include <vector>

#include "PatternDecoder.h"

namespace {

uint32_t updateCrc32(uint32_t crc, uint8_t byte) {
    crc ^= byte;
    for (uint8_t bit = 0; bit < 8; ++bit) {
        crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return crc;
}

bool expect(
    PatternDecodeResult actual,
    PatternDecodeResult expected,
    const char* description
) {
    if (actual == expected) {
        return true;
    }
    std::cerr
        << description << ": expected " << patternDecodeResultMessage(expected)
        << ", got " << patternDecodeResultMessage(actual) << '\n';
    return false;
}

bool verifyAsset(const PatternAssets::Asset& asset, const char* name) {
    std::vector<uint16_t> row(asset.width);
    uint32_t crc = 0xFFFFFFFFu;
    for (uint16_t y = 0; y < asset.height; ++y) {
        const PatternDecodeResult result =
            decodePatternRow(asset, y, row.data(), row.size());
        if (result != PatternDecodeResult::Ok) {
            std::cerr
                << name << " row " << y << ": "
                << patternDecodeResultMessage(result) << '\n';
            return false;
        }
        for (const uint16_t pixel : row) {
            crc = updateCrc32(crc, static_cast<uint8_t>(pixel));
            crc = updateCrc32(crc, static_cast<uint8_t>(pixel >> 8));
        }
    }
    crc ^= 0xFFFFFFFFu;
    if (crc != asset.decodedCrc32) {
        std::cerr
            << name << ": expected CRC32 0x" << std::hex << asset.decodedCrc32
            << ", got 0x" << crc << std::dec << '\n';
        return false;
    }
    return true;
}

bool verifyErrorHandling() {
    using PatternAssets::Asset;
    using PatternAssets::kColourBars;
    std::array<uint16_t, 320> row = {};
    bool success = true;

    success &= expect(
        decodePatternRow(kColourBars, 0, nullptr, row.size()),
        PatternDecodeResult::NullDestination,
        "null destination"
    );
    success &= expect(
        decodePatternRow(kColourBars, kColourBars.height, row.data(), row.size()),
        PatternDecodeResult::RowOutOfRange,
        "row range"
    );
    success &= expect(
        decodePatternRow(kColourBars, 0, row.data(), row.size() - 1),
        PatternDecodeResult::DestinationTooSmall,
        "destination capacity"
    );

    Asset modified = kColourBars;
    modified.codecVersion += 1;
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::UnsupportedCodecVersion,
        "codec version"
    );

    modified = kColourBars;
    modified.payloadSize += 1;
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::InvalidMetadata,
        "payload accounting"
    );

    modified = kColourBars;
    std::vector<uint8_t> rowMap(
        kColourBars.rowMap,
        kColourBars.rowMap + kColourBars.height
    );
    rowMap[0] = static_cast<uint8_t>(kColourBars.uniqueRowCount);
    modified.rowMap = rowMap.data();
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::InvalidRowIndex,
        "row dictionary index"
    );

    modified = kColourBars;
    std::vector<uint16_t> rowOffsets(
        kColourBars.rowOffsets,
        kColourBars.rowOffsets + kColourBars.uniqueRowCount + 1
    );
    rowOffsets[0] = 1;
    modified.rowOffsets = rowOffsets.data();
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::InvalidRowOffsets,
        "row offsets"
    );

    modified = kColourBars;
    std::vector<uint8_t> rowData(
        kColourBars.rowData,
        kColourBars.rowData + kColourBars.rowDataSize
    );
    rowData[kColourBars.rowOffsets[kColourBars.rowMap[0]]] =
        static_cast<uint8_t>(kColourBars.paletteSize);
    modified.rowData = rowData.data();
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::InvalidPaletteIndex,
        "palette index"
    );

    modified = kColourBars;
    rowData.assign(
        kColourBars.rowData,
        kColourBars.rowData + kColourBars.rowDataSize
    );
    rowData[kColourBars.rowOffsets[kColourBars.rowMap[0]] + 1] = 0;
    modified.rowData = rowData.data();
    success &= expect(
        decodePatternRow(modified, 0, row.data(), row.size()),
        PatternDecodeResult::InvalidRunLength,
        "zero run length"
    );

    return success;
}

}  // namespace

int main() {
    bool success = true;
    for (size_t index = 0; index < PatternAssets::kCount; ++index) {
        success &= verifyAsset(
            *PatternAssets::kAll[index],
            PatternAssets::kNames[index]
        );
    }
    success &= verifyErrorHandling();
    if (!success) {
        return 1;
    }
    std::cout
        << "Decoded all " << PatternAssets::kCount
        << " firmware assets and verified decoder error handling.\n";
    return 0;
}
