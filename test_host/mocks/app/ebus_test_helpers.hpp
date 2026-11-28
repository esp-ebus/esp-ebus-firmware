// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <vector>

#include "app/ebus_accessor.hpp"

inline bool configureHostEbusController() {
  auto& controller = getEbusController();
  if (controller.isConfigured()) return true;

  auto config = getEbusConfig();
  config.bus.device = "/dev/null";
  return controller.configure(config);
}

// Tracks outbound queue sessions and cancels them again on scope exit. Host
// tests never run the controller thread, so nothing would ever drain the
// queue: fill() additionally fills the queue to capacity for tests that need
// a rejection or a full-queue replacement, and track() keeps sessions queued
// by the test itself for the cleanup.
struct QueueGuard {
  bool fill() {
    if (!getEbusController().isConfigured()) return false;
    const uint8_t message[] = {0x50, 0xb5, 0x09, 0x04, 0x0e, 0x33, 0x00, 0x00};
    for (unsigned i = 0; i < 1024; ++i) {
      const uint32_t id = getEbusController().enqueue(
          app::priority::send, ebus::ByteView(message, sizeof(message)));
      if (id == 0) return true;  // Queue is full.
      ids.push_back(id);
    }
    return false;
  }

  // Keep a session created outside fill() for cancellation on scope exit.
  void track(uint32_t session_id) {
    if (session_id != 0) ids.push_back(session_id);
  }

  ~QueueGuard() {
    for (const uint32_t id : ids) getEbusController().cancel(id);
  }

  std::vector<uint32_t> ids;
};
