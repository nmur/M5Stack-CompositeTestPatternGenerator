#!/bin/sh
set -eu

task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_binary=$(mktemp "${TMPDIR:-/tmp}/scanline-renderer-test.XXXXXX")
trap 'rm -f "$task_binary"' EXIT HUP INT TERM

"${CXX:-c++}" -std=c++11 -Wall -Wextra -Werror -pedantic \
  -I "$task_root/include" \
  "$task_root/tools/tests/scanline_renderer_test.cpp" \
  "$task_root/src/ScanlineRenderer.cpp" \
  "$task_root/src/ImageScaler.cpp" \
  -o "$task_binary"
"$task_binary"
