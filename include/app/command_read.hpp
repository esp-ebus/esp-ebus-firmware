// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "app/command.hpp"
#include "app/ebus_accessor.hpp"

// Passive read patterns may be incomplete telegrams and must never be sent.
inline bool requestCommandRead(Command& command) {
  if (!command.getActive()) return false;
  uint8_t read_buf[10];
  const size_t read_len = command.buildReadCmd(read_buf, sizeof(read_buf));
  if (read_len == 0) return false;
  const auto id = getEbusController().enqueue(
      app::priority::send, ebus::ByteView(read_buf, read_len),
      command.getPendingReadId());
  if (id == 0) return false;
  command.setPendingReadId(id);
  return true;
}
