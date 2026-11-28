"""Verify semantic HA profile assignment for fields."""

import json
import unittest
from pathlib import Path

import mapper
from model import CommandIR, FamilyIR, FieldIR

ROOT = Path(__file__).resolve().parents[2]
UNIT_ASSIGNMENTS = (
    ("°C", "sensor_temperature"),
    ("K", "sensor_temperature"),
    ("bar", "sensor_pressure"),
    ("Pa", "sensor_pressure"),
    ("mbar", "sensor_pressure"),
    ("l/min", "sensor_flow"),
    ("l/h", "sensor_flow"),
    ("m³/h", "sensor_flow"),
    ("m3/h", "sensor_flow"),
    ("l/s", "sensor_flow"),
    ("W", "sensor_power"),
    ("kW", "sensor_power"),
    ("kWh", "sensor_energy"),
    ("MWh", "sensor_energy"),
    ("V", "sensor_voltage"),
    ("A", "sensor_current"),
    ("Hz", "sensor_frequency"),
    ("dBm", "sensor_rssi"),
)


class SemanticHAProfileTests(unittest.TestCase):
    def test_read_units_map_to_registered_sensor_profiles(self):
        profiles = json.loads(
            (ROOT / "profiles" / "ha_profiles.json").read_text(encoding="utf-8")
        )
        profile_names = {profile["name"] for profile in profiles}

        for unit, name in UNIT_ASSIGNMENTS:
            with self.subTest(unit=unit):
                field = FieldIR(name="reading", unit=unit)
                self.assertEqual(mapper._semantic_ha_profile(field, "read"), name)
                self.assertIn(name, profile_names)

    def test_writes_are_not_mislabeled_as_read_sensors(self):
        field = FieldIR(name="targetTemperature", unit="°C")
        self.assertEqual(mapper._semantic_ha_profile(field, "write"), "")

    def test_ambiguous_percentages_are_left_unassigned(self):
        field = FieldIR(name="pumpPower", unit="%")
        self.assertEqual(mapper._semantic_ha_profile(field, "read"), "")

    def test_humidity_and_total_names_use_semantic_profiles(self):
        humidity = FieldIR(name="relativeHumidity", unit="%")
        total = FieldIR(name="totalOperatingHours", unit="h")
        self.assertEqual(
            mapper._semantic_ha_profile(humidity, "read"),
            "sensor_humidity",
        )
        self.assertEqual(mapper._semantic_ha_profile(total, "read"), "sensor_total")

    def test_only_ordered_boolean_enums_become_switches_or_binary_sensors(self):
        on_off = [
            {"key": "off", "value": 0},
            {"key": "on", "value": 1},
        ]
        profiles = json.loads(
            (ROOT / "profiles" / "ha_profiles.json").read_text(encoding="utf-8")
        )
        profile_names = {profile["name"] for profile in profiles}
        field = FieldIR(name="status", meta={"values": on_off})
        self.assertEqual(mapper._semantic_ha_profile(field, "read"), "binary_sensor")
        self.assertEqual(mapper._semantic_ha_profile(field, "write"), "switch")
        self.assertIn("switch", profile_names)

        inverted = [
            {"key": "on", "value": 0},
            {"key": "off", "value": 1},
        ]
        field.meta["values"] = inverted
        self.assertEqual(mapper._semantic_ha_profile(field, "read"), "")

        field.meta["values"] = [
            {"key": "auto", "value": 0},
            {"key": "manual", "value": 1},
            {"key": "holiday", "value": 2},
        ]
        self.assertEqual(mapper._semantic_ha_profile(field, "read"), "")
        self.assertEqual(mapper._semantic_ha_profile(field, "write"), "")

    def test_scalar_enum_values_are_resolved_before_assignment(self):
        entries = [
            {"key": "off", "value": 0},
            {"key": "on", "value": 1},
        ]
        raw = {
            "registers": [
                {
                    "name": "OnOffStatus",
                    "register": "b5090103",
                    "rw": "read",
                    "fields": [{"name": "value", "ebus_type": "onoff"}],
                }
            ],
            "scalars": {
                "onoff": {
                    "base_type": "UCH",
                    "values_enum": "Values_onoff",
                }
            },
            "enums": {"Values_onoff": {"entries": entries}},
        }

        family = mapper.build_profiles_and_commands(raw)
        command = family.commands[0]
        self.assertEqual(command.fields[0].meta["values"], entries)
        result = mapper.commands_to_flat_entries(family)
        self.assertEqual(result[0]["fields"][0]["ha_profile"], "binary_sensor")

    def test_bit_fields_remain_binary_sensors(self):
        field = FieldIR(name="status", meta={"bits": {"active": 0, "fault": 1}})
        self.assertEqual(mapper._semantic_ha_profile(field, "read"), "binary_sensor")

    def test_generated_fields_use_semantic_unit_profile(self):
        family = FamilyIR(
            commands=[
                CommandIR(
                    name="OutsideTemperature",
                    rw="read",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="EXP",
                            unit="°C",
                            our_datatype="FLOAT32",
                        )
                    ],
                )
            ]
        )
        result = mapper.commands_to_flat_entries(family)
        self.assertEqual(result[0]["fields"][0]["ha_profile"], "sensor_temperature")


if __name__ == "__main__":
    unittest.main()
