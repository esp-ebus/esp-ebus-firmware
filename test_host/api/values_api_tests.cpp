// SPDX-License-Identifier: GPL-3.0-or-later
#define private public
#define protected public
#include <catch2/catch_test_macros.hpp>
#include <string>

#include "api/values_api.hpp"
#include "app/command.hpp"
#include "app/command_manager.hpp"
#include "app/ebus_test_helpers.hpp"
#undef private
#undef protected

namespace {

std::string makeCommandJson() {
  return R"({
    "key":"01",
    "name":"Outside_Temperature",
    "read_cmd":"50b509030d3300",
    "write_cmd":"50b509050e3300",
    "interval":60,
    "master":false,
    "fields":[
      {"name":"value","profile":"data2b_celsius","position":1,"ha_profile":"sensor_temperature"}
    ]
  })";
}

void insertTestCommand() {
  command_manager.wipeCommands();
  const std::string command_json = makeCommandJson();
  ebus::detail::JsonReader reader(command_json);
  Command command = Command::fromJson(reader);
  command_manager.insertCommand(std::move(command));
}

}  // namespace

TEST_CASE("ValuesApi serves the values page", "[values_api]") {
  command_manager.wipeCommands();
  ValuesApi api(command_manager);
  httpd_req_t req{};

  REQUIRE(ValuesApi::handleValuesPage(&req) == ESP_OK);
  REQUIRE(req.status == "200 OK");
  REQUIRE(req.content_type == "text/html");
  REQUIRE(req.final_body == "<html><body>values</body></html>");
}

TEST_CASE("ValuesApi reads and writes by key", "[values_api]") {
  REQUIRE(configureHostEbusController());
  insertTestCommand();
  REQUIRE(command_manager.findCommand("01") != nullptr);

  ValuesApi api(command_manager);
  QueueGuard queue;  // Cancel the sessions this test puts on the queue.

  httpd_req_t read_req{};
  read_req.body = R"({"key":"01"})";
  read_req.content_len = static_cast<int>(read_req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&read_req) == ESP_OK);
  REQUIRE(read_req.status == "200 OK");
  REQUIRE(command_manager.findCommand("01")->getPendingReadId() != 0);
  queue.track(command_manager.findCommand("01")->getPendingReadId());
  REQUIRE(read_req.content_type == "application/json;charset=utf-8");
  REQUIRE(read_req.final_body.find(R"("id":"read")") != std::string::npos);
  REQUIRE(read_req.final_body.find(R"("status":"requested")") !=
          std::string::npos);

  // A one-shot reply has no poll_id; it must still update the active command.
  const uint8_t response[] = {2, 0, 21};  // DATA2B: 21 degrees
  ebus::ProtocolInfo info{};
  info.session_id = command_manager.findCommand("01")->getPendingReadId();
  info.slave_view = ebus::ByteView(response, sizeof(response));
  command_manager.updateData(info);
  REQUIRE(command_manager.findCommand("01")->getData().size() == 2);
  REQUIRE(command_manager.findCommand("01")->getData()[1] == 21);
  REQUIRE(command_manager.findCommand("01")->getPendingReadId() == 0);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"01","value":12.5})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "200 OK");
  REQUIRE(write_req.final_body.find(R"("id":"write")") != std::string::npos);
  REQUIRE(write_req.final_body.find(R"("status":"successful")") !=
          std::string::npos);

  auto* command = command_manager.findCommand("01");
  REQUIRE(command->getWriteSessionId() != 0);
  REQUIRE(command->getPendingReadId() == 0);
  queue.track(command->getWriteSessionId());
  ebus::ProtocolInfo write_result{};
  write_result.session_id = command->getWriteSessionId();
  command_manager.handleWriteResult(write_result);
  REQUIRE(command->getWriteSessionId() == 0);
  REQUIRE(command->getPendingReadId() != 0);
  queue.track(command->getPendingReadId());

  httpd_req_t list_req{};
  REQUIRE(ValuesApi::handleValues(&list_req) == ESP_OK);
  REQUIRE(list_req.content_type == "application/json;charset=utf-8");
  std::string values_body;
  for (const auto& chunk : list_req.chunks) values_body += chunk;
  REQUIRE(values_body.find(R"("key":"01")") != std::string::npos);
  REQUIRE(values_body.find(R"("name":"Outside_Temperature")") !=
          std::string::npos);
  REQUIRE(list_req.chunks.back().empty());

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi writes a fieldless command with key only",
          "[values_api]") {
  REQUIRE(configureHostEbusController());
  command_manager.wipeCommands();
  const std::string command_json =
      R"({"key":"stop","name":"Ioteststop","zz":"08","wpbsb":"b506","wdx":"01",)"
      R"("interval":0,"master":false,"fields":[]})";
  ebus::detail::JsonReader reader(command_json);
  command_manager.insertCommand(Command::fromJson(reader));
  ValuesApi api(command_manager);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"stop"})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "200 OK");
  REQUIRE(write_req.final_body.find(R"("status":"successful")") !=
          std::string::npos);
  QueueGuard queue;  // Cancel the queued write on scope exit.
  queue.track(command_manager.findCommand("stop")->getWriteSessionId());

  httpd_req_t valued_req{};
  valued_req.body = R"({"key":"stop","value":1})";
  valued_req.content_len = static_cast<int>(valued_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&valued_req) == ESP_OK);
  REQUIRE(valued_req.status == "400 Bad Request");

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi still requires values for fieldful commands",
          "[values_api]") {
  insertTestCommand();
  ValuesApi api(command_manager);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"01"})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "400 Bad Request");

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects unknown keys", "[values_api]") {
  command_manager.wipeCommands();
  ValuesApi api(command_manager);

  httpd_req_t read_req{};
  read_req.body = R"({"key":"missing"})";
  read_req.content_len = static_cast<int>(read_req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&read_req) == ESP_OK);
  REQUIRE(read_req.status == "404 Not Found");
  REQUIRE(read_req.final_body.find(R"("id":"read")") != std::string::npos);
  REQUIRE(read_req.final_body.find("Key 'missing' not found") !=
          std::string::npos);

  httpd_req_t write_req{};
  write_req.body = R"({"key":"missing","value":12.5})";
  write_req.content_len = static_cast<int>(write_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&write_req) == ESP_OK);
  REQUIRE(write_req.status == "404 Not Found");
  REQUIRE(write_req.final_body.find(R"("id":"write")") != std::string::npos);
  REQUIRE(write_req.final_body.find("Key 'missing' not found") !=
          std::string::npos);
}

TEST_CASE("ValuesApi rejects malformed and invalid writes", "[values_api]") {
  insertTestCommand();
  ValuesApi api(command_manager);

  httpd_req_t malformed_req{};
  malformed_req.body = R"({"key":"01","value":)";
  malformed_req.content_len = static_cast<int>(malformed_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&malformed_req) == ESP_OK);
  REQUIRE(malformed_req.status == "400 Bad Request");
  REQUIRE(malformed_req.final_body.find(R"("status":"failed")") !=
          std::string::npos);

  httpd_req_t invalid_value_req{};
  invalid_value_req.body = R"({"key":"01","value":"not-a-number"})";
  invalid_value_req.content_len =
      static_cast<int>(invalid_value_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&invalid_value_req) == ESP_OK);
  REQUIRE(invalid_value_req.status == "400 Bad Request");
  REQUIRE(invalid_value_req.final_body.find(R"("id":"write")") !=
          std::string::npos);
  REQUIRE(invalid_value_req.final_body.find("Invalid value for key '01'") !=
          std::string::npos);

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi writes multi-field commands with a value object",
          "[values_api]") {
  REQUIRE(configureHostEbusController());
  command_manager.wipeCommands();
  const std::string command_json = R"({
    "key": "mf",
    "name": "MultiField",
    "zz": "50",
    "id": "0301",
    "wid": "b5090400",
    "interval": 60,
    "master": false,
    "fields": [
      {"name": "a", "profile": "uint8", "position": 1, "ha_profile": ""},
      {"name": "b", "profile": "uint16", "position": 2, "ha_profile": ""}
    ]
  })";
  ebus::detail::JsonReader reader(command_json);
  command_manager.insertCommand(Command::fromJson(reader));
  REQUIRE(command_manager.findCommand("mf") != nullptr);
  ValuesApi api(command_manager);

  httpd_req_t ok_req{};
  ok_req.body = R"({"key":"mf","value":{"b":258,"a":7}})";
  ok_req.content_len = static_cast<int>(ok_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&ok_req) == ESP_OK);
  REQUIRE(ok_req.status == "200 OK");
  REQUIRE(ok_req.final_body.find(R"("status":"successful")") !=
          std::string::npos);
  QueueGuard queue;  // Cancel the queued write on scope exit.
  queue.track(command_manager.findCommand("mf")->getWriteSessionId());

  // Incomplete object: rejected at the request level, nothing enqueued.
  httpd_req_t incomplete_req{};
  incomplete_req.body = R"({"key":"mf","value":{"a":7}})";
  incomplete_req.content_len = static_cast<int>(incomplete_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&incomplete_req) == ESP_OK);
  REQUIRE(incomplete_req.status == "400 Bad Request");
  REQUIRE(incomplete_req.final_body.find("Invalid value for key 'mf'") !=
          std::string::npos);

  // Scalar on a multi-field command: rejected (would truncate to field 0).
  httpd_req_t scalar_req{};
  scalar_req.body = R"({"key":"mf","value":7})";
  scalar_req.content_len = static_cast<int>(scalar_req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&scalar_req) == ESP_OK);
  REQUIRE(scalar_req.status == "400 Bad Request");

  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects sending passive match patterns", "[values_api]") {
  command_manager.wipeCommands();
  const std::string json =
      R"({"key":"passive","name":"Room","read_cmd":"51501407","interval":0,"master":true,"fields":[{"name":"value","profile":"data2b_celsius","position":4}]})";
  ebus::detail::JsonReader reader(json);
  command_manager.insertCommand(Command::fromJson(reader));
  ValuesApi api(command_manager);
  httpd_req_t req{};
  req.body = R"({"key":"passive"})";
  req.content_len = static_cast<int>(req.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&req) == ESP_OK);
  REQUIRE(req.status == "400 Bad Request");
  REQUIRE(command_manager.findCommand("passive")->getPendingReadId() == 0);
  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi rejects writes when the bus queue is full",
          "[values_api]") {
  REQUIRE(configureHostEbusController());
  insertTestCommand();
  QueueGuard queue;
  REQUIRE(queue.fill());

  auto* command = command_manager.findCommand("01");
  REQUIRE(command != nullptr);
  command->setLast(123);

  ValuesApi api(command_manager);
  httpd_req_t req{};
  req.body = R"({"key":"01","value":12.5})";
  req.content_len = static_cast<int>(req.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&req) == ESP_OK);
  REQUIRE(req.status == "503 Service Unavailable");
  REQUIRE(req.final_body.find("Unable to queue write command") !=
          std::string::npos);
  REQUIRE(req.final_body.find(R"("status":"successful")") == std::string::npos);
  REQUIRE(command->getLast() == 123);
  REQUIRE(command->getWriteSessionId() == 0);
  REQUIRE(command->getPendingReadId() == 0);
  command_manager.wipeCommands();
}

TEST_CASE("ValuesApi supersedes a pending write when the queue is full",
          "[values_api]") {
  REQUIRE(configureHostEbusController());
  insertTestCommand();
  ValuesApi api(command_manager);
  auto* command = command_manager.findCommand("01");

  httpd_req_t first{};
  first.body = R"({"key":"01","value":12.5})";
  first.content_len = static_cast<int>(first.body.size());
  REQUIRE(ValuesApi::handleValuesWrite(&first) == ESP_OK);
  REQUIRE(first.status == "200 OK");
  const auto previous = command->getWriteSessionId();
  REQUIRE(previous != 0);
  QueueGuard cleanup;  // Cancel sessions queued by this test on scope exit.
  cleanup.track(previous);

  {
    QueueGuard queue;
    REQUIRE(queue.fill());

    // The second write frees the first write's slot, so it is accepted even
    // though the queue is full.
    httpd_req_t second{};
    second.body = R"({"key":"01","value":13.0})";
    second.content_len = static_cast<int>(second.body.size());
    REQUIRE(ValuesApi::handleValuesWrite(&second) == ESP_OK);
    REQUIRE(second.status == "200 OK");
    const auto current = command->getWriteSessionId();
    REQUIRE(current != 0);
    REQUIRE(current != previous);
    queue.track(current);

    // The superseded write's result must not trigger a readback.
    ebus::ProtocolInfo stale{};
    stale.session_id = previous;
    command_manager.handleWriteResult(stale);
    REQUIRE(command->getWriteSessionId() == current);
    REQUIRE(command->getPendingReadId() == 0);
  }

  // Queue drained: the current write's result requests the readback.
  ebus::ProtocolInfo result{};
  result.session_id = command->getWriteSessionId();
  command_manager.handleWriteResult(result);
  REQUIRE(command->getWriteSessionId() == 0);
  REQUIRE(command->getPendingReadId() != 0);
  cleanup.track(command->getPendingReadId());
  command_manager.wipeCommands();
}

TEST_CASE(
    "A second manual read supersedes the pending one when the queue is full",
    "[values_api]") {
  REQUIRE(configureHostEbusController());
  insertTestCommand();
  ValuesApi api(command_manager);
  auto* command = command_manager.findCommand("01");

  httpd_req_t first{};
  first.body = R"({"key":"01"})";
  first.content_len = static_cast<int>(first.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&first) == ESP_OK);
  REQUIRE(first.status == "200 OK");
  const auto pending = command->getPendingReadId();
  REQUIRE(pending != 0);

  QueueGuard queue;
  REQUIRE(queue.fill());

  // The second read replaces the queued one instead of being rejected.
  httpd_req_t second{};
  second.body = R"({"key":"01"})";
  second.content_len = static_cast<int>(second.body.size());
  REQUIRE(ValuesApi::handleValuesRead(&second) == ESP_OK);
  REQUIRE(second.status == "200 OK");
  const auto superseding = command->getPendingReadId();
  REQUIRE(superseding != 0);
  REQUIRE(superseding != pending);
  queue.track(superseding);

  // The superseded session's reply must not update the command.
  const uint8_t response[] = {2, 0, 21};  // DATA2B: 21 degrees
  ebus::ProtocolInfo stale{};
  stale.session_id = pending;
  stale.slave_view = ebus::ByteView(response, sizeof(response));
  command_manager.updateData(stale);
  REQUIRE(command->getPendingReadId() == superseding);
  REQUIRE(command->getData().empty());

  // The current session's reply updates and clears the pending id.
  ebus::ProtocolInfo reply{};
  reply.session_id = superseding;
  reply.slave_view = ebus::ByteView(response, sizeof(response));
  command_manager.updateData(reply);
  REQUIRE(command->getPendingReadId() == 0);
  REQUIRE(command->getData().size() == 2);
  REQUIRE(command->getData()[1] == 21);

  command_manager.wipeCommands();
}
