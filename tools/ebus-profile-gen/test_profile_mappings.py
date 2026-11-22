"""Verify corpus unit mappings resolve to canonical data profiles."""

import json
import unittest
from pathlib import Path

from mapper import _map_profile_name

ROOT = Path(__file__).resolve().parents[2]
UNIT_MAPPINGS = (
    ("DATA1C", "h", 1, "data1c_hour"),
    ("UINT16", "l/min", 100, "uint16_lpm_div100"),
    ("UINT16R", "ppm", 1, "uint16r_ppm"),
    ("UINT16R", "m³/h", 1, "uint16r_m3h"),
    ("INT16", "kW", 10, "int16_kw_div10"),
    ("FLOAT32", "h", 1, "float32_hour"),
    ("INT16", "°min", 1, "int16_degree_min"),
    ("UINT16", "U/sec", 1, "uint16_u_per_sec"),
    ("FLOAT32", "rps", 1, "float32_rps"),
    ("INT16R", "V", 10, "int16r_volt_div10"),
    ("INT16R", "m³/h", 1, "int16r_m3h"),
    ("INT8", "kW", 10, "int8_kw_div10"),
    ("UINT16", "l/min", 1000, "uint16_lpm_div1000"),
    ("UINT16", "ppm", 1, "uint16_ppm"),
    ("UINT16R", "Pa", 10, "uint16r_pa_div10"),
    ("UINT16R", "h", 5, "uint16r_hour_div5"),
    ("UINT16R", "rpm", 1, "uint16r_rpm"),
    ("DATA2C", "bar", 4, "data2c_bar_div4"),
    ("FLOAT32", "W", 1, "float32_w"),
    ("FLOAT32", "kW", 1000, "float32_kw_div1000"),
    ("INT16", "U/s", 10, "int16_u_per_s_div10"),
    ("INT16", "l/min", 10, "int16_lpm_div10"),
    ("UINT16", "MWh", 1, "uint16_mwh"),
    ("UINT16", "Pa", 1, "uint16_pa"),
    ("UINT16", "V", 100, "uint16_volt_div100"),
    ("UINT16", "bar", 1, "uint16_bar"),
    ("UINT16", "bar", 10, "uint16_bar_div10"),
    ("UINT16", "kOhm", 1, "uint16_kohm"),
    ("UINT16R", "days", 1, "uint16r_days"),
    ("UINT16R", "m³", 1000, "uint16r_m3_div1000"),
    ("UINT32", "mbar", 1, "uint32_mbar"),
    ("UINT16", "Hz", 1, "uint16_hz"),
    ("UINT16", "days", 1, "uint16_days"),
    ("UINT16", "l/s", 12, "uint16_lps_div12"),
    ("UINT16", "m", 1, "uint16_m"),
    ("UINT32", "min", 120, "uint32_min_div120"),
    ("UINT8", "°min", 300, "uint8_degree_min_div300"),
)


class UnitProfileMappingTests(unittest.TestCase):
    def test_corpus_unit_combinations_map_to_canonical_profiles(self):
        profiles = json.loads(
            (ROOT / "profiles" / "data_profiles.json").read_text(encoding="utf-8")
        )
        by_name = {profile["name"]: profile for profile in profiles}

        self.assertEqual(len(UNIT_MAPPINGS), 37)
        for datatype, unit, divider, name in UNIT_MAPPINGS:
            with self.subTest(datatype=datatype, unit=unit, divider=divider):
                self.assertLessEqual(len(name), 24)
                self.assertEqual(
                    _map_profile_name(datatype, unit, divider=divider), name
                )
                profile = by_name[name]
                self.assertEqual(
                    (profile["datatype"], profile["unit"], profile["divider"]),
                    (datatype, unit, divider),
                )


if __name__ == "__main__":
    unittest.main()
