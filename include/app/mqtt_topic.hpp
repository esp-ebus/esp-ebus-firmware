// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cctype>
#include <cstddef>

// PascalCase / camelCase → snake_case, in place.
// Returns the new length (may be larger than `len` due to inserted '_').
// The buffer must have room for up to 2×len−1 bytes (worst case: every char
// is uppercase). No null terminator is written — the caller owns that.
// '/' characters are replaced with '_' so command keys containing slashes
// do not create MQTT subtopics.
//
// Examples:
//   CompStartsHwc        → comp_starts_hwc
//   ABCDef               → abc_def
//   already_snake        → already_snake  (no-op)
//   heatpump/compressor  → heatpump_compressor
inline size_t toSnakeCase(char* buf, size_t len) {
  char tmp[128];
  size_t j = 0;
  for (size_t i = 0; i < len && j < 127; ++i) {
    const unsigned char c = static_cast<unsigned char>(buf[i]);
    if (c == '/') {
      // Replace path separator with underscore; collapse consecutive '/'
      // or '/' immediately after '_' to avoid double underscores.
      if (j > 0 && tmp[j - 1] != '_') tmp[j++] = '_';
    } else if (std::isupper(c)) {
      const char prev = (i > 0) ? buf[i - 1] : '\0';
      const char next = (i + 1 < len) ? buf[i + 1] : '\0';
      const bool prevLower = std::islower(static_cast<unsigned char>(prev));
      const bool prevDigit = std::isdigit(static_cast<unsigned char>(prev));
      const bool nextLower = std::islower(static_cast<unsigned char>(next));
      if (j > 0 && (prevLower || prevDigit) && prev != '_') {
        tmp[j++] = '_';
      } else if (j > 0 && prev != '_' &&
                 std::isupper(static_cast<unsigned char>(prev)) && nextLower) {
        tmp[j++] = '_';
      }
      tmp[j++] = static_cast<char>(std::tolower(c));
    } else {
      tmp[j++] = static_cast<char>(c);
    }
  }
  for (size_t i = 0; i < j; ++i) buf[i] = tmp[i];
  return j;
}
