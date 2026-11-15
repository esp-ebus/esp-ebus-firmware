#!/usr/bin/env python3
"""Golden id/wid/position assertions for the ebus-profile generator.

Verifies resolved read/write addressing of representative commands against
the archived CSV ground truth (concatenation model: template PBSB +
base D bytes + member ext), BI byte-grouping (consecutive BI0..BI7 runs
collapse to one UINT8 field carrying a `bits` name->bit map), write-only
commands with an empty id, 1-based byte positions of fields, and composite
expansion field shapes (plain models → positioned leaves). It also checks
that TypeSpec field metadata reaches command fields and matching data
profiles. Run from the repo root:

    python3 tools/ebus-profile-gen/test_golden_ids.py
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mapper  # noqa: E402
import resolver  # noqa: E402
import tsp_parser  # noqa: E402
from convlog import NULL_LOG  # noqa: E402
from model import CommandIR, FamilyIR, FieldIR  # noqa: E402

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_EBUSD_ROOT = os.path.join(_REPO_ROOT, "tools", "ebus-profile-gen", "ebusd-configuration")
_TYPESPEC_ROOT = os.path.join(_REPO_ROOT, "tools", "ebus-profile-gen", "ebus-typespec")

_failures: List[str] = []
_checks = 0


def family_for(tsp_rel: str) -> Tuple[Dict[str, Any], FamilyIR, List[str]]:
    """Resolve and parse one tsp input into its raw IR and family."""
    res = resolver.IncludeResolver(_EBUSD_ROOT, _TYPESPEC_ROOT)
    files = res.resolve(tsp_rel)
    raw = tsp_parser.TspParser(files).parse()
    fam = mapper.build_profiles_and_commands(raw, log=NULL_LOG)
    return raw, fam, files


def entries_for(tsp_rel: str) -> Dict[str, List[Dict[str, Any]]]:
    """Run the generate.py pipeline in-process and index entries by name."""
    raw, fam, files = family_for(tsp_rel)
    # Key prefix mirrors generate.py: the tsp stem verbatim, lowercased
    # (52.mc2.mc.4 → "52.mc2.mc.4_"). The leading "NN." is the slave
    # address and is kept — it is the only thing that disambiguates
    # same-named registers across units (FlowTemp in 52 vs 53).
    stem = os.path.splitext(os.path.basename(tsp_rel))[0]
    prefix = f"{stem.lower()}_" if stem else ""

    # Derive default ZZ mirroring generate.py
    default_zz: int = 0x08
    stem_m = re.match(r"^([0-9a-fA-F]{2})\.", stem)
    if stem_m:
        default_zz = int(stem_m.group(1), 16)
    elif files:
        try:
            with open(files[0], "r", encoding="utf-8") as f:
                content = f.read()
            comm_m = re.search(r"//\s*@zz\(([^)]+)\)", content)
            if comm_m:
                val_str = comm_m.group(1).strip()
                default_zz = int(val_str, 0)
        except Exception:
            pass

    entries = mapper.commands_to_flat_entries(
        fam,
        key_prefix=prefix,
        aliases=raw.get("aliases", {}),
        log=NULL_LOG,
        default_zz=default_zz,
    )
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_name.setdefault(e["name"], []).append(e)
    return by_name


def profile_outputs_for(
    tsp_rel: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return generated profiles and commands for metadata assertions."""
    raw, fam, _ = family_for(tsp_rel)
    profiles = mapper.profiles_to_flat_entries(fam, log=NULL_LOG)
    commands = mapper.commands_to_flat_entries(
        fam, aliases=raw.get("aliases", {}), log=NULL_LOG
    )
    return profiles, commands


def expect(
    by_name: Dict[str, List[Dict[str, Any]]],
    name: str,
    id_hex: Optional[str],
    wid_hex: Optional[str] = None,
) -> None:
    """Assert read/write addressing for a command against ground truth.

    Entries carry the split schema (pbsb/dx, wpbsb/wdx); assertions still
    speak in concatenated id/wid hex so the archived-CSV constants stay
    byte-identical to the pre-split golden file.
    """
    global _checks
    _checks += 1
    entries = by_name.get(name)

    def _read_id(e: Dict[str, Any]) -> str:
        return (e.get("pbsb") or "") + (e.get("dx") or "")

    def _write_id(e: Dict[str, Any]) -> str:
        return (e.get("wpbsb") or "") + (e.get("wdx") or "")

    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        if wid_hex is None:
            assert all(
                _read_id(e) == id_hex and not _write_id(e) for e in entries
            ), f"{name}: expected id={id_hex!r} read-only, got " + str(
                [(_read_id(e), _write_id(e)) for e in entries]
            )
        else:
            assert all(
                _read_id(e) == id_hex and _write_id(e) == wid_hex
                for e in entries
            ), f"{name}: expected id={id_hex!r} wid={wid_hex!r}, got " + str(
                [(_read_id(e), _write_id(e)) for e in entries]
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_absent(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, why: str = ""
) -> None:
    global _checks
    _checks += 1
    try:
        assert not by_name.get(name), (
            f"{name}: expected absent{(' (' + why + ')') if why else ''}, "
            f"got {[(e.get('pbsb'), e.get('dx')) for e in by_name[name]]}"
        )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_zz(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, zz_hex: str
) -> None:
    """Assert the destination byte for a command (archived ZZ column)."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        assert all(e.get("zz") == zz_hex for e in entries), (
            f"{name}: expected zz={zz_hex!r}, got "
            + str([e.get("zz") for e in entries])
        )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_positions(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, positions: List[int]
) -> None:
    """Assert 1-based byte positions of a command's fields.

    Positions are data-part byte offsets (firmware: field_pos = position-1),
    so successors of a multi-byte field shift accordingly.
    """
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = [f["position"] for f in e["fields"]]
            assert got == positions, (
                f"{name}: expected positions={positions}, got {got}"
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_fields(
    by_name: Dict[str, List[Dict[str, Any]]], name: str, field_names: List[str]
) -> None:
    """Assert the exact field-name list of a command (expansion shape)."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = [f["name"] for f in e["fields"]]
            assert got == field_names, (
                f"{name}: expected fields={field_names}, got {got}"
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_bits(
    by_name: Dict[str, List[Dict[str, Any]]],
    name: str,
    field_name: str,
    bits: Dict[str, int],
) -> None:
    """Assert the `bits` map of a byte-grouped (BI0..BI7) field."""
    global _checks
    _checks += 1
    entries = by_name.get(name)
    try:
        assert entries, (
            f"{name}: command missing (present: {sorted(by_name)})"
        )
        for e in entries:
            got = {
                f["name"]: f.get("bits")
                for f in e["fields"]
                if "bits" in f
            }
            assert got.get(field_name) == bits, (
                f"{name}: expected bits[{field_name!r}]={bits}, "
                f"got {got.get(field_name)}"
            )
            bits_field = next(
                (f for f in e["fields"] if f["name"] == field_name), None
            )
            assert bits_field is not None and (
                bits_field.get("ha_profile") == "binary_sensor"
            ), (
                f"{name}: bits field {field_name!r} must carry "
                f"ha_profile=binary_sensor, got "
                f"{bits_field.get('ha_profile') if bits_field else None!r}"
            )
    except AssertionError as exc:
        _failures.append(str(exc))


def expect_profile_metadata(
    profiles: List[Dict[str, Any]],
    commands: List[Dict[str, Any]],
    command_name: str,
    field_values: Dict[str, Any],
    profile_values: Dict[str, Any],
    field_name: Optional[str] = None,
) -> None:
    """Assert field metadata and its referenced profile carry expected values."""
    global _checks
    _checks += 1
    try:
        command = next(c for c in commands if c["name"] == command_name)
        fields = [
            f for f in command["fields"]
            if field_name is None or f["name"] == field_name
        ]
        assert len(fields) == 1, (
            f"{command_name}: expected one matching field, got {fields}"
        )
        field = fields[0]
        for key, value in field_values.items():
            assert field.get(key) == value, (
                f"{command_name}: expected field {key}={value!r}, "
                f"got {field.get(key)!r}"
            )
        profile = next(
            (p for p in profiles if p["name"] == field["profile"]), None
        )
        assert profile is not None, (
            f"{command_name}: profile {field['profile']!r} was not emitted"
        )
        for key, value in profile_values.items():
            assert profile.get(key) == value, (
                f"{command_name}: expected profile {key}={value!r}, "
                f"got {profile.get(key)!r}"
            )
    except (AssertionError, StopIteration) as exc:
        _failures.append(f"{command_name}: {exc}")


def expect_distinct_profile_refs(
    commands: List[Dict[str, Any]], first_name: str, second_name: str
) -> None:
    """Assert metadata variants reference distinct generated profiles."""
    global _checks
    _checks += 1
    try:
        first = next(c for c in commands if c["name"] == first_name)
        second = next(c for c in commands if c["name"] == second_name)
        assert first["fields"][0]["profile"] != second["fields"][0]["profile"], (
            f"{first_name} and {second_name} share a profile despite different metadata"
        )
    except (AssertionError, StopIteration) as exc:
        _failures.append(f"profile variants: {exc}")


def expect_unit_profile_mappings() -> None:
    """Assert unit profiles are selected only when their scaling matches."""
    global _checks
    _checks += 1
    try:
        family = FamilyIR(
            commands=[
                CommandIR(
                    name="SignedTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="INT16",
                            unit="°C",
                            factor="10",
                        )
                    ],
                ),
                CommandIR(
                    name="UnsignedTemperature",
                    fields=[
                        FieldIR(name="value", ebus_type="UINT16", unit="°C")
                    ],
                ),
                CommandIR(
                    name="UnscaledSignedTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="INT16",
                            unit="°C",
                            factor="1",
                        )
                    ],
                ),
                CommandIR(
                    name="ScaledUnsignedTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="UINT16",
                            unit="°C",
                            factor="10",
                        )
                    ],
                ),
                CommandIR(
                    name="FloatTemperature",
                    fields=[
                        FieldIR(name="value", ebus_type="FLOAT32", unit="°C")
                    ],
                ),
                CommandIR(
                    name="HalfScaledSignedTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="INT16",
                            unit="°C",
                            factor="2",
                        )
                    ],
                ),
                CommandIR(
                    name="ReverseSignedTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="INT16R",
                            unit="°C",
                            factor="10",
                        )
                    ],
                ),
                CommandIR(
                    name="ScaledDataTemperature",
                    fields=[
                        FieldIR(
                            name="value",
                            ebus_type="DATA2C",
                            unit="°C",
                            factor="16",
                        )
                    ],
                ),
            ]
        )
        profiles = mapper.profiles_to_flat_entries(family, log=NULL_LOG)
        commands = mapper.commands_to_flat_entries(family, log=NULL_LOG)
        profile_by_name = {profile["name"]: profile for profile in profiles}
        command_by_name = {command["name"]: command for command in commands}

        expected = {
            "SignedTemperature": ("int16_celsius_div10", 10),
            "UnsignedTemperature": ("uint16_celsius", 1),
            "UnscaledSignedTemperature": ("int16_celsius", 1),
            "ScaledUnsignedTemperature": ("uint16_celsius_div10", 10),
            "FloatTemperature": ("float32_celsius", 1),
            "HalfScaledSignedTemperature": ("int16_celsius_div2", 2),
            "ReverseSignedTemperature": ("int16r_celsius_div10", 10),
            "ScaledDataTemperature": ("data2c_celsius_div16", 16),
        }
        for command_name, (profile_name, divider) in expected.items():
            field_profile = command_by_name[command_name]["fields"][0]["profile"]
            assert field_profile == profile_name, (
                f"{command_name}: expected {profile_name!r}, got {field_profile!r}"
            )
            profile = profile_by_name[field_profile]
            assert profile["divider"] == divider, (
                f"{command_name}: expected divider {divider}, "
                f"got {profile['divider']!r}"
            )
    except (AssertionError, KeyError) as exc:
        _failures.append(f"unit profile mapping: {exc}")


def main() -> int:
    # hcmode_inc: @inherit chains, BI gate, no fabricated 0x0d.
    hcmode = entries_for("src/vaillant/hcmode_inc.tsp")
    expect(hcmode, "DateTime", "b50400")
    expect(hcmode, "Status16", "b50416")
    expect(hcmode, "Status01", "b51101")
    expect(hcmode, "Status02", "b51102")
    expect(hcmode, "Status", "b51103")
    expect(hcmode, "StatusCirPump", "b51200", "b51200")
    expect(hcmode, "wm", "", "b505")
    expect(hcmode, "SetMode", "b51000", "b51000")
    expect_absent(hcmode, "rm", "inherited via date_time")

    # iotesthp_inc: write-only commands carry wid only.
    iotesthp = entries_for("src/vaillant/iotesthp_inc.tsp")
    expect(iotesthp, "Iotest", "", "b50602")
    expect(iotesthp, "Ioteststop", "", "b50601")
    expect(iotesthp, "rm", "b504")
    expect(iotesthp, "wm", "", "b505")

    # errors_inc: @base D-byte tails, write-only clear.
    errors = entries_for("src/vaillant/errors_inc.tsp")
    expect(errors, "Currenterror", "b5030001")
    expect(errors, "Errorhistory", "b5030101")
    expect(errors, "Clearerrorhistory", "", "b5030201")

    # 05.vd4: wid inheritance through is-template flatten, BI gate.
    vd4 = entries_for("src/vaillant/05.vd4.tsp")
    expect(vd4, "EnableMonitoring", "b5090d0100", "b5090e0100")
    expect(vd4, "SwitchRelays", "b5090d2700", "b5090e2700")
    expect(vd4, "ActualDigitalInputs", "b5090d3a00", "b5090e3a00")
    expect_zz(vd4, "EnableMonitoring", "05")

    # 08.ehp: concat ids, imported models, phase NOT gated.
    ehp = entries_for("src/vaillant/08.ehp.tsp")
    expect(ehp, "CompStartsHwc", "b5090da800")
    expect(ehp, "PhaseStatus", "b5090d8800")
    expect(ehp, "DateTime", "b50400")
    expect(ehp, "Iotest", "", "b50602")
    expect(ehp, "Clearerrorhistory", "", "b5030201")
    expect(ehp, "SetMode", "b51000", "b51000")
    expect_zz(ehp, "CompStartsHwc", "08")
    expect_zz(ehp, "HwcTemp", "25")

    # broadcast: b/wi write side shares the base tail; archived ZZ is FE
    # (alias BROADCAST = Targets.broadcast resolves via union constants).
    broadcast = entries_for("src/vaillant/broadcast.tsp")
    expect(broadcast, "Vdatetime", "b51600", "b51600")
    expect(broadcast, "Outsidetemp", "b51601")
    expect(broadcast, "HwcStatus", "b50527")
    expect(broadcast, "Load", "b50506")
    expect_zz(broadcast, "Vdatetime", "fe")
    expect_zz(broadcast, "Outsidetemp", "fe")
    expect_zz(hcmode, "DateTime", "08")

    # 15.e7c: is-template + @ext variadic ids/wids.
    e7c = entries_for("src/vaillant/15.e7c.tsp")
    expect(e7c, "HeatingScheduleEnable", "b5090d0200", "b5090e0200")
    expect(e7c, "MondayHeatingTime", "b5090d0500", "b5090e0500")
    expect_zz(e7c, "HeatingScheduleEnable", "15")

    # 15.392: timer PBSB (B515) and per-direction PBSB (r B504 / w B505).
    t392 = entries_for("src/vaillant/15.392.tsp")
    expect(t392, "CcTimer_Monday", "b5150002", "b5150002")
    expect(t392, "Setpoints_Monday", "b5041901", "b5052e01")
    expect_zz(t392, "CcTimer_Monday", "15")

    # Byte positions: 1-based data-part offsets, not field ordinals —
    # successors of multi-byte fields shift (char3@2 → char4@5 → d2b@9).
    expect_positions(hcmode, "DateTime", [1, 2, 5, 9])
    expect_positions(broadcast, "Vdatetime", [1, 4])
    expect_positions(e7c, "MondayHeatingTemp", [1, 3, 5, 7, 9, 11, 13])

    # Composite expansion: plain models become positioned leaf sub-fields
    # (full field path joined with '_'); consecutive BI0..BI7 runs collapse
    # into one UINT8 field carrying the `bits` name->bit map.
    expect_fields(
        errors, "Currenterror",
        ["value_error", "value_error_1", "value_error_2",
         "value_error_3", "value_error_4"],
    )
    expect_positions(errors, "Currenterror", [1, 3, 5, 7, 9])
    expect_fields(
        errors, "Errorhistory",
        ["index", "errorhistory_status", "errorhistory_time",
         "errorhistory_date", "errorhistory_error"],
    )
    expect_positions(errors, "Errorhistory", [1, 2, 3, 5, 8])
    expect_fields(
        t392, "CcTimer_Monday",
        ["value_slot1_slot_from", "value_slot1_slot_to",
         "value_slot1_slot_1_from", "value_slot1_slot_1_to",
         "value_slot1_slot_2_from", "value_slot1_slot_2_to",
         "value_daysel"],
    )
    expect_positions(t392, "CcTimer_Monday", [1, 2, 3, 4, 5, 6, 7])
    expect_fields(ehp, "PhaseStatus", ["value_phase"])
    expect_bits(
        ehp, "PhaseStatus", "value_phase",
        {"value_phase": 0, "value_phase_1": 1, "value_phase_2": 2},
    )
    expect_fields(
        hcmode, "SetMode",
        ["hcmode", "flowtempdesired", "hwctempdesired", "hwcflowtempdesired",
         "ign", "disablehc", "ign_1", "remoteControlHcPump"],
    )
    expect_positions(hcmode, "SetMode", [1, 2, 3, 4, 5, 6, 7, 8])
    expect_bits(
        hcmode, "SetMode", "disablehc",
        {"disablehc": 0, "disablehwctapping": 1, "disablehwcload": 2},
    )
    expect_bits(
        hcmode, "SetMode", "remoteControlHcPump",
        {"remoteControlHcPump": 0, "releaseBackup": 1, "releaseCooling": 2},
    )
    expect_fields(
        ehp, "SetMode",
        ["hcmode", "flowtempdesired", "hwctempdesired", "hwcflowtempdesired",
         "ign", "disablehc", "ign_1", "remoteControlHcPump"],
    )
    expect_fields(vd4, "SwitchRelays", ["bi"])
    expect_positions(vd4, "SwitchRelays", [1])
    expect_bits(vd4, "SwitchRelays", "bi", {"bi": 0, "bi_1": 1})
    expect_fields(vd4, "ActualDigitalInputs", ["bi"])
    expect_positions(vd4, "ActualDigitalInputs", [1])
    expect_bits(vd4, "ActualDigitalInputs", "bi", {"bi": 0, "bi_1": 1})

    # Field-level metadata is emitted on both command fields and the
    # corresponding profile; differing limits/precision must not deduplicate.
    ctlv2_profiles, ctlv2_commands = profile_outputs_for(
        "src/vaillant/15.ctlv2.tsp"
    )
    expect_profile_metadata(
        ctlv2_profiles,
        ctlv2_commands,
        "CylinderChargeHyst",
        {"min": 3, "max": 20},
        {"unit": "K", "digits": 1, "min": 3, "max": 20},
    )
    expect_profile_metadata(
        ctlv2_profiles,
        ctlv2_commands,
        "CylinderChargeOffset",
        {"min": 0, "max": 40},
        {"unit": "K", "digits": 0, "min": 0, "max": 40},
    )
    expect_distinct_profile_refs(
        ctlv2_commands, "CylinderChargeHyst", "CylinderChargeOffset"
    )
    expect_unit_profile_mappings()

    ehp_profiles, ehp_commands = profile_outputs_for("src/vaillant/08.ehp.tsp")
    expect_profile_metadata(
        ehp_profiles,
        ehp_commands,
        "HwcTemp",
        {"min": -50, "max": 180},
        {"unit": "°C", "digits": 1, "min": -50, "max": 180},
        field_name="value_temp",
    )
    expect_profile_metadata(
        ehp_profiles,
        ehp_commands,
        "ActualEnvironmentPowerFine",
        {},
        {"unit": "kW", "divider": 10.0, "digits": 0, "min": 0, "max": 0},
    )

    if _failures:
        print(f"FAIL: {_failures.__len__()}/{_checks} checks failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"OK: {_checks} generator checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
