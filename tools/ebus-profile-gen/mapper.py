"""Map tsp IR to our internal IR and group into profiles/commands."""

from __future__ import annotations

import re
from typing import Any

try:
    from .convlog import NULL_LOG
    from .model import CommandIR, FamilyIR, FieldIR, ProfileIR
except ImportError:
    from convlog import NULL_LOG
    from model import CommandIR, FamilyIR, FieldIR, ProfileIR


# Mapping from eBUS TypeSpec base types to our datatypes
# These are the base types from ebus-typespec/lib/types.tsp
TYPE_MAP: dict[str, str] = {
    # 1 byte types
    "UCH": "UINT8",
    "SCH": "INT8",
    "D1B": "DATA1B",  # 1-byte signed fixed-point (ebus::DataType::data1b)
    "D1C": "DATA1C",  # 1-byte unsigned fixed-point /2 (ebus::DataType::data1c)
    "BCD": "BCD8",
    "HCD": "UINT8",  # 1-byte HCD: no native library type, treat as raw UINT8
    "BI0": "UINT8",
    "BI1": "UINT8",
    "BI2": "UINT8",
    "BI3": "UINT8",
    "BI4": "UINT8",
    "BI5": "UINT8",
    "BI6": "UINT8",
    "BI7": "UINT8",
    "BI0_6": "UINT8",
    "BI0_7": "UINT8",
    "U1L": "UINT8",
    "S1L": "INT8",
    "INT8": "INT8",
    "UINT8": "UINT8",
    # 2 byte types
    "PIN": "PIN2",  # 2-byte BCD reversed, "0077" string output
    "TEM_P": "TEM_P",  # 2-byte parameter id "GG-NNN" string output
    "UIN": "UINT16",
    "UIR": "UINT16R",
    "U2L": "UINT16",
    "U2B": "UINT16R",
    "SIN": "INT16",
    "SIR": "INT16R",
    "S2L": "INT16",
    "S2B": "INT16R",
    "BCD2": "BCD16",  # 2-byte BCD digit pairs, little-endian pairs
    "HCD2": "HEX2",  # 2-byte HCD digit bytes (0x00-0x63 each) → raw hex
    "D2B": "DATA2B",  # 2-byte signed fixed-point /256 (ebus::DataType::data2b)
    "D2C": "DATA2C",  # 2-byte signed fixed-point /16 (ebus::DataType::data2c)
    "FLT": "INT16",  # 2-byte /1000 — INT16; no dedicated FLT type
    "FLR": "INT16R",  # same, big-endian
    "INT16": "INT16",
    "UINT16": "UINT16",
    # 3 byte types — U3N/S3N families have native 24-bit DataTypes;
    # the no-sentinel U3L/U3B/S3L/S3B variants do not
    "BCD3": "BCD24",  # 3-byte BCD (cntstarts, cnthours): native 6-digit BCD
    "HCD3": "HEX3",  # 3-byte HCD digit bytes; no native decode → raw hex
    "U3N": "UINT24",
    "U3R": "UINT24R",
    "U3L": "HEX3",
    "U3B": "HEX3",
    "S3N": "INT24",
    "S3R": "INT24R",
    "S3L": "HEX3",
    "S3B": "HEX3",
    "INT32": "INT32",
    "UINT32": "UINT32",
    # 4 byte types
    "ULG": "UINT32",
    "ULR": "UINT32R",
    "U4L": "UINT32",
    "U4B": "UINT32R",
    "SLG": "INT32",
    "SLR": "INT32R",
    "S4L": "INT32",
    "S4B": "INT32R",
    "BCD4": "BCD32",  # 4-byte BCD digit pairs; HCD4 stays raw hex
    "HCD4": "HEX4",
    "EXP": "FLOAT32",
    "EXR": "FLOAT32R",
    "FLOAT4": "FLOAT32",
    "FLOAT4R": "FLOAT32R",
    # String types — @maxLength handled by _map_type(); fallback CHAR1/HEX1
    "STR": "CHAR1",
    "NTS": "CHAR1",
    "IGN": "CHAR1",
    "HEX": "HEX1",
    "CHAR1": "CHAR1",
    "CHAR2": "CHAR2",
    "CHAR3": "CHAR3",
    "CHAR4": "CHAR4",
    "CHAR5": "CHAR5",
    "CHAR6": "CHAR6",
    "CHAR7": "CHAR7",
    "CHAR8": "CHAR8",
    "CHAR9": "CHAR9",
    "CHAR10": "CHAR10",
    "CHAR11": "CHAR11",
    "CHAR12": "CHAR12",
    "CHAR13": "CHAR13",
    "CHAR14": "CHAR14",
    "CHAR15": "CHAR15",
    "CHAR16": "CHAR16",
    "HEX1": "HEX1",
    "HEX2": "HEX2",
    "HEX3": "HEX3",
    "HEX4": "HEX4",
    "HEX5": "HEX5",
    "HEX6": "HEX6",
    "HEX7": "HEX7",
    "HEX8": "HEX8",
    "HEX9": "HEX9",
    "HEX10": "HEX10",
    "HEX11": "HEX11",
    "HEX12": "HEX12",
    "HEX13": "HEX13",
    "HEX14": "HEX14",
    "HEX15": "HEX15",
    "HEX16": "HEX16",
    # Boolean/bit — no native BOOL DataType; boolean → UINT8
    "boolean": "UINT8",
    "BOOL": "UINT8",
    # Date/time types — native string-semantic DataTypes; BDY/HDY weekday
    # pairs stay raw until their text formats land.
    "BTI": "TIME_BCD3R",  # 3-byte BCD time, wire SS MM HH
    "HTI": "TIME_BIN3",  # 3-byte decimal time, wire HH MM SS
    "VTI": "TIME_BIN3R",  # 3-byte decimal time, wire SS MM HH [Vaillant]
    "BTM": "TIME_BCD2R",  # 2-byte BCD time, wire MM HH
    "HTM": "TIME_BIN2",  # 2-byte decimal time, wire HH MM
    "VTM": "TIME_BIN2R",  # 2-byte decimal time hh:mm, wire MM HH [Vaillant]
    "MIN": "TIME_MIN2",  # 2-byte minutes since midnight (LE)
    "TTM": "TIME_TRUNC10",  # 1-byte truncated time (/10 min)
    "TTH": "TIME_TRUNC30",  # 6-bit truncated time (/30 min)
    "TTQ": "TIME_TRUNC15",  # 7-bit truncated time (/15 min)
    "BDA": "DATE_BCD4",  # 4-byte BCD date with weekday
    "HDA": "DATE_BIN4",  # 4-byte decimal date with weekday
    "BDA3": "DATE_BCD3",  # 3-byte BCD date
    "HDA3": "DATE_BIN3",  # 3-byte decimal date
    "BDZ": "DATE_BCD4Z",  # 4-byte BCD date with zero-based weekday
    "DAY": "DATE_DAY2",  # 2-byte days since 1900-01-01
    "DTM": "DATETIME_MIN4",  # 4-byte minutes since 2009-01-01
    "BDY": "UINT8",  # 1-byte weekday (Mon=0)
    "HDY": "UINT8",  # 1-byte weekday [Vaillant] (Mon=1)
}

# Byte size per ebus-library DataType name (matches ebus::DataType enum high byte).
# Used to compute the eBUS write NN byte: NN = 3 + data_byte_count.
DATATYPE_SIZE: dict[str, int] = {
    # 1 byte
    "BCD8": 1,
    "UINT8": 1,
    "INT8": 1,
    "DATA1B": 1,
    "DATA1C": 1,
    "CHAR1": 1,
    "HEX1": 1,
    "TIME_TRUNC10": 1,
    "TIME_TRUNC15": 1,
    "TIME_TRUNC30": 1,
    # 2 bytes
    "UINT16": 2,
    "UINT16R": 2,
    "INT16": 2,
    "INT16R": 2,
    "DATA2B": 2,
    "DATA2BR": 2,
    "DATA2C": 2,
    "DATA2CR": 2,
    "CHAR2": 2,
    "HEX2": 2,
    "BCD16": 2,
    "PIN2": 2,
    "TIME_BIN2R": 2,
    "TIME_BIN2": 2,
    "TIME_MIN2": 2,
    "TIME_BCD2R": 2,
    "DATE_DAY2": 2,
    "TEM_P": 2,
    # 3 bytes
    "UINT24": 3,
    "UINT24R": 3,
    "INT24": 3,
    "INT24R": 3,
    "CHAR3": 3,
    "HEX3": 3,
    "BCD24": 3,
    "DATE_BIN3": 3,
    "DATE_BCD3": 3,
    "TIME_BIN3": 3,
    "TIME_BCD3R": 3,
    "TIME_BIN3R": 3,
    # 4 bytes
    "UINT32": 4,
    "UINT32R": 4,
    "INT32": 4,
    "INT32R": 4,
    "FLOAT32": 4,
    "FLOAT32R": 4,
    "BCD32": 4,
    "CHAR4": 4,
    "HEX4": 4,
    "DATE_BCD4": 4,
    "DATE_BCD4Z": 4,
    "DATE_BIN4": 4,
    "DATETIME_MIN4": 4,
    # 5-8 bytes
    "CHAR5": 5,
    "HEX5": 5,
    "CHAR6": 6,
    "HEX6": 6,
    "CHAR7": 7,
    "HEX7": 7,
    "CHAR8": 8,
    "HEX8": 8,
    # 9-16 bytes (TypeSpec defines these via @maxLength on STR/HEX). The
    # protocol caps NN at 16 data bytes (spec 5.6, max_data_bytes), so
    # nothing wider than 16 can occur on the wire — no rows beyond this.
    "CHAR9": 9,
    "HEX9": 9,
    "CHAR10": 10,
    "HEX10": 10,
    "CHAR11": 11,
    "HEX11": 11,
    "CHAR12": 12,
    "HEX12": 12,
    "CHAR13": 13,
    "HEX13": 13,
    "CHAR14": 14,
    "HEX14": 14,
    "CHAR15": 15,
    "HEX15": 15,
    "CHAR16": 16,
    "HEX16": 16,
}

# ebus-library native DataTypes it can actually decode/encode.
# Anything not in this set cannot be turned into a data profile.
# Source of truth: ebus::DataType enum in include/ebus/data_types.hpp.
SUPPORTED_DATATYPES: set = {
    # 1 byte
    "BCD8",
    "UINT8",
    "INT8",
    "DATA1B",
    "DATA1C",
    "CHAR1",
    "HEX1",
    "TIME_TRUNC10",
    "TIME_TRUNC15",
    "TIME_TRUNC30",
    # 2 bytes
    "UINT16",
    "UINT16R",
    "INT16",
    "INT16R",
    "DATA2B",
    "DATA2BR",
    "DATA2C",
    "DATA2CR",
    "CHAR2",
    "HEX2",
    "BCD16",
    "PIN2",
    "TIME_BIN2R",
    "TIME_BIN2",
    "TIME_MIN2",
    "TIME_BCD2R",
    "DATE_DAY2",
    "TEM_P",
    # 3 bytes
    "UINT24",
    "UINT24R",
    "INT24",
    "INT24R",
    "CHAR3",
    "HEX3",
    "BCD24",
    "DATE_BIN3",
    "DATE_BCD3",
    "TIME_BIN3",
    "TIME_BCD3R",
    "TIME_BIN3R",
    # 4 bytes
    "UINT32",
    "UINT32R",
    "INT32",
    "INT32R",
    "FLOAT32",
    "FLOAT32R",
    "BCD32",
    "CHAR4",
    "HEX4",
    "DATE_BCD4",
    "DATE_BCD4Z",
    "DATE_BIN4",
    "DATETIME_MIN4",
    # 5-8 bytes
    "CHAR5",
    "HEX5",
    "CHAR6",
    "HEX6",
    "CHAR7",
    "HEX7",
    "CHAR8",
    "HEX8",
    # 9-16 bytes
    "CHAR9",
    "HEX9",
    "CHAR10",
    "HEX10",
    "CHAR11",
    "HEX11",
    "CHAR12",
    "HEX12",
    "CHAR13",
    "HEX13",
    "CHAR14",
    "HEX14",
    "CHAR15",
    "HEX15",
    "CHAR16",
    "HEX16",
}

# Mapping from ebusd-configuration scalar names to our datatypes
# These are from _templates.tsp and device-specific includes
SCALAR_TYPE_MAP: dict[str, str] = {
    # Counter types
    "cntstarts": "BCD24",  # BCD3 -> native 6-digit BCD
    "cntstarts2": "UINT16",  # UIN -> 2-byte unsigned
    "cntminutes": "BCD8",  # BCD -> 1 byte
    "cnthours": "BCD24",  # BCD3 -> native 6-digit BCD
    "cntfuel": "BCD32",  # BCD4 -> native 8-digit BCD
    # Temperature types
    "temp": "DATA2C",  # D2C -> 2-byte signed with special handling
    "temp0": "UINT8",  # UCH -> 1 byte unsigned
    "temp1": "DATA1C",  # D1C -> 1-byte signed with special handling
    "temp2": "DATA2B",  # D2B -> 2-byte signed with special handling
    "tempsensor": "DATA2C",  # typically D2C
    "tempmirrorsensor": "UINT16",  # UIN
    "desiredtemp": "UINT8",  # UCH
    "outsidetemp": "INT8",  # SCH
    # Pressure types
    "press": "DATA2B",  # D2B
    "presssensor": "DATA2B",  # typically D2B
    # Percentage types
    "percent": "DATA2C",  # D2C with % unit
    "percent0": "UINT8",  # UCH with % unit
    "percent1": "DATA1C",  # D1C with % unit
    "percent2": "DATA2B",  # D2B with % unit
    "percents": "INT8",  # SCH with % unit
    # Status/on-off types
    "onoff": "UINT8",
    "onoff2": "UINT8",
    "yesno": "UINT8",
    "yesno2": "UINT8",
    "errorok": "UINT8",
    "phase": "UINT8",
    "phaseok": "UINT8",
    "dcfstate": "UINT8",
    # Energy types
    "energy4": "UINT32",  # typically ULG
    "energy": "UINT16",  # UIN
    "integral": "INT16",  # SIN
    # Flow / speed
    "fanspeed": "UINT16",  # UIN
    "fanspeedoffset": "INT16",  # SIN
    "flowrate": "UINT16",  # UIN
    "flowrate100": "UINT16",  # UIN
    "airflowrate": "UINT16",  # UIN
    "speed": "UINT16",  # UIN
    # Time
    "hoursum": "UINT32",  # ULG -> 4 bytes
    "hoursum2": "UINT16",  # UIN -> 2 bytes
    "hours": "UINT8",  # HCD / UCH -> 1 byte
    "hours1": "DATA1C",  # D1C -> 1 byte / 2
    "minutes": "UINT16",  # UIN
    "minutes0": "UINT8",  # UCH
    "minutes2": "UINT16",  # UIN
    "seconds": "UINT32",  # ULG
    "seconds0": "UINT8",  # UCH
    "seconds2": "UINT16",  # UIN
    "seconds4": "UINT32",  # ULG
    # Unit/string types
    "unit": "UINT8",
    "fueltype": "UINT8",
    "countertype": "UINT8",
    "opdatacyclic": "UINT8",
    "opdatatransfer": "UINT8",
    "opdataheat": "UINT8",
    "opdataaction": "UINT8",
    "mcmode": "UINT8",
    "power": "UINT8",
    # Calibration
    "calibration": "DATA2C",  # D2C
    "calibration0": "UINT8",  # UCH
    "calibration1": "DATA1C",  # D1C
    "calibrations": "INT8",  # SCH
    # Misc numeric
    "uin100": "UINT16",  # UIN
    "version": "UINT16",
    "pressm2": "UINT16",  # UIN
    "curve": "UINT16",  # UIN
    "frequency": "UINT16",  # UIN
    # Skip/ignore
    "skip": "UINT8",
    # String types
    "IGN": "CHAR1",
}

# Known enum types that map to UINT8
ENUM_TYPES: dict[str, str] = {
    "Values_unit": "UINT8",
    "Values_fueltype": "UINT8",
    "Values_countertype": "UINT8",
    "Values_opdatacyclic": "UINT8",
    "Values_opdatatransfer": "UINT8",
    "Values_opdataheat": "UINT8",
    "Values_opdataaction": "UINT8",
}

# Single-field template models and their field names
_SINGLE_FIELD_TEMPLATES = {
    "ReadonlyRegister",
    "ReadonlyUpdateRegister",
    "WriteRegister",
    "InstallRegister",
    "ServiceCommandRegister",
}

_TWO_FIELD_TEMPLATES = {
    "ServiceUpdateRegister",
}

# Template models whose instances are writable on the eBUS bus (respond to
# write commands, NN=0x04) unless explicitly marked @passive.
_WRITABLE_TEMPLATES = {
    "WriteRegister",
    "InstallRegister",
    "ServiceCommandRegister",
    "UpdateRegister",
    "InstallUpdateRegister",
    "ServiceUpdateRegister",
}

# eBUS bitfield types: BI0..BI7 are individual bits (ebus-typespec
# `scalar BI0 extends boolean`), phase1..3 extend them, and plain boolean
# fields are bit payloads too. The firmware command writer packs at most
# 4 bytes per field and cannot emit these wire payloads faithfully, so any
# command carrying one is dropped (resolved type "boolean"/"BOOL" as well
# as the raw scalar names when the typespec library is not loaded).
_BIT_GATED_EBUS_TYPES = frozenset(
    {"boolean", "BOOL"} | {f"BI{i}" for i in range(8)} | {"phase1", "phase2", "phase3"}
)


def _bit_index(ebus_type: str) -> int | None:
    """Bit number of a BI0..BI7 type, else None."""
    t = _strip_qualified(ebus_type)
    if t.startswith("BI") and t[2:].isdigit():
        n = int(t[2:])
        if n <= 7:
            return n
    return None


def _merge_bit_runs(fields: list[FieldIR]) -> list[FieldIR]:
    """Collapse each consecutive BI0..BI7 run into one byte-wide UINT8 field.

    The bits of a run share a single wire byte, which byte-positioned fields
    cannot represent individually: keep the first member's name, carry the
    whole run as a `bits` name->bit-index map in meta, and count it as one
    UINT8 byte for positions and NN.
    """
    merged: list[FieldIR] = []
    i = 0
    while i < len(fields):
        if _bit_index(fields[i].ebus_type) is None:
            merged.append(fields[i])
            i += 1
            continue
        run: list[FieldIR] = []
        while i < len(fields) and _bit_index(fields[i].ebus_type) is not None:
            run.append(fields[i])
            i += 1
        head = run[0]
        merged.append(
            FieldIR(
                name=head.name,
                ebus_type="UINT8",
                unit=head.unit,
                factor=head.factor,
                offset=head.offset,
                length=1,
                signed=head.signed,
                big_endian=head.big_endian,
                bitfield=True,
                bitpos=0,
                bitlen=8,
                mask=head.mask,
                our_datatype="UINT8",
                meta={
                    **head.meta,
                    "bits": {f.name: _bit_index(f.ebus_type) for f in run},
                },
            )
        )
    return merged


def _strip_qualified(ebus_type: str) -> str:
    """Strip namespace qualification from a type name (Ebus.Num.UCH -> UCH)."""
    t = (ebus_type or "").strip()
    if "." in t:
        t = t.split(".")[-1]
    return t


def _map_type(ebus_type: str, max_length: int | None = None) -> str:
    """Map an eBUS TypeSpec type to our datatype string.

    For STR/HEX/IGN types the @maxLength decorator selects the exact
    CHAR/HEX width (e.g. STR + maxLength(21) → CHAR21, IGN +
    maxLength(7) → CHAR7). The protocol allows at most 16 data bytes
    (spec 5.6, max_data_bytes) and the ebus-library implements
    CHAR1-16 / HEX1-16; wider types are flagged as unsupported by the caller.
    """
    t = _strip_qualified(ebus_type)
    mapped = TYPE_MAP.get(t)
    if mapped:
        if t in ("STR", "HEX", "IGN") and max_length:
            base = "HEX" if t == "HEX" else "CHAR"
            return f"{base}{max_length}"
        return mapped
    # Try scalar type map (for named scalars like tempsensor, cntstarts, etc.)
    return SCALAR_TYPE_MAP.get(t, ebus_type.upper() if ebus_type else "")


def _classify_type(
    ebus_type: str, datatype: str, enums: dict[str, Any] | None = None
) -> str:
    """Classify a TypeSpec type for the conversion log.

    Returns one of: native, profile, unsupported, defaulted.

    Classification is based on the mapped ebus-library datatype; CHAR/HEX
    types wider than 16 bytes are unsupported because the protocol allows
    at most 16 data bytes (spec 5.6, max_data_bytes) — CHAR17+ cannot
    occur on the wire.
    """
    t = _strip_qualified(ebus_type)
    d = _strip_qualified(datatype)
    # CHAR/HEX width check on the mapped datatype (STR/HEX with @maxLength)
    if d.startswith(("CHAR", "HEX")):
        try:
            prefix = "CHAR" if d.startswith("CHAR") else "HEX"
            width = int(d[len(prefix) :])
        except ValueError:
            width = 0
        if width > 16:
            return "unsupported"
    if t in TYPE_MAP:
        return "native"
    if t in SCALAR_TYPE_MAP:
        return "profile"
    if enums and t in enums:
        # Enum types resolve to UINT8 (native), not "unsupported".
        # They decode correctly on the wire; flag as native so validation
        # doesn't reject them.
        return "native"
    return "defaulted"


UNIT_PROFILE_BASES: dict[tuple[str, str], str] = {
    ("DATA1C", "h"): "data1c_hour",
    ("UINT16", "l/min"): "uint16_lpm",
    ("UINT16R", "ppm"): "uint16r_ppm",
    ("UINT16R", "m³/h"): "uint16r_m3h",
    ("INT16", "kw"): "int16_kw",
    ("FLOAT32", "h"): "float32_hour",
    ("INT16", "°min"): "int16_degree_min",
    ("UINT16", "u/sec"): "uint16_u_per_sec",
    ("FLOAT32", "rps"): "float32_rps",
    ("INT16R", "v"): "int16r_volt",
    ("INT16R", "m³/h"): "int16r_m3h",
    ("INT8", "kw"): "int8_kw",
    ("UINT16", "ppm"): "uint16_ppm",
    ("UINT16R", "pa"): "uint16r_pa",
    ("UINT16R", "h"): "uint16r_hour",
    ("UINT16R", "rpm"): "uint16r_rpm",
    ("DATA2C", "bar"): "data2c_bar",
    ("FLOAT32", "w"): "float32_w",
    ("FLOAT32", "kw"): "float32_kw",
    ("INT16", "u/s"): "int16_u_per_s",
    ("INT16", "l/min"): "int16_lpm",
    ("UINT16", "mwh"): "uint16_mwh",
    ("UINT16", "pa"): "uint16_pa",
    ("UINT16", "v"): "uint16_volt",
    ("UINT16", "bar"): "uint16_bar",
    ("UINT16", "kohm"): "uint16_kohm",
    ("UINT16R", "days"): "uint16r_days",
    ("UINT16R", "m³"): "uint16r_m3",
    ("UINT32", "mbar"): "uint32_mbar",
    ("UINT16", "hz"): "uint16_hz",
    ("UINT16", "days"): "uint16_days",
    ("UINT16", "l/s"): "uint16_lps",
    ("UINT16", "m"): "uint16_m",
    ("UINT32", "min"): "uint32_min",
    ("UINT8", "°min"): "uint8_degree_min",
}


def _map_profile_name(
    ebus_type: str,
    unit: str,
    max_length: int | None = None,
    divider: float = 1.0,
) -> str:
    """Map a field's ebus_type and unit to a profile name in data_profiles.json.

    This uses the datatype, unit, and divider to determine the appropriate
    profile name.
    """
    # Get the mapped datatype
    datatype = _map_type(ebus_type, max_length)
    unit_lower = (unit or "").strip().lower()

    # Special mappings based on type + unit combinations
    # Temperature
    if (
        ("celsius" in unit_lower or unit_lower == "°c" or unit_lower == "c")
        and datatype in SUPPORTED_DATATYPES
        and datatype.startswith(("DATA", "INT", "UINT", "FLOAT"))
    ):
        profile_name = f"{datatype.lower()}_celsius"
        if divider != 1:
            divider_name = format(divider, "g").replace(".", "p")
            profile_name += f"_div{divider_name}"
        return profile_name

    # Pressure
    if unit_lower == "bar":
        if datatype == "DATA2B":
            return "data2b_bar"
        if datatype == "FLOAT32":
            return "float32_bar"
        if datatype == "INT16":
            return "int16_bar"

    # Percentage
    if unit_lower in ("%", "percent"):
        if datatype == "INT16":
            return "int16_percent"
        if datatype == "INT16R":
            return (
                f"int16r_percent_div{format(divider, 'g').replace('.', 'p')}"
                if divider != 1
                else "int16r_percent"
            )
        if datatype == "UINT8":
            return "uint8_percent"
        if datatype == "UINT16":
            return "uint16_percent"
        if datatype == "UINT16R":
            return "uint16r_percent"
        if datatype == "DATA1C":
            return "data1c_percent"
        if datatype == "DATA2C":
            return "data2c_percent"
        if datatype == "FLOAT32":
            return "float32_percent"
        if datatype == "INT8":
            return "int8_percent_div10"

    # Power
    if unit_lower == "kw":
        if datatype == "UINT8":
            return "uint8_kw"
        if datatype == "UINT16":
            return "uint16_kw_div10"

    # Energy
    if unit_lower == "kwh":
        if datatype == "UINT32":
            return "uint32_kwh"
        if datatype == "UINT16":
            return (
                f"uint16_kwh_div{format(divider, 'g').replace('.', 'p')}"
                if divider != 1
                else "uint16_kwh"
            )
        if datatype == "FLOAT32":
            return (
                f"float32_kwh_div{format(divider, 'g').replace('.', 'p')}"
                if divider != 1
                else "float32_kwh"
            )

    # Flow rate
    if unit_lower in ("l/min", "lpm") and datatype == "DATA2C":
        return "data2c_lpm"
    if unit_lower == "l/h" and datatype == "UINT16":
        return "uint16_lph"
    if unit_lower == "m3/h" and datatype == "UINT16":
        return "uint16_m3h"

    # Time
    if unit_lower == "h" or unit_lower == "hour":
        if datatype == "UINT32":
            return "uint32_hour"
        if datatype == "UINT16":
            return "uint16_hour"
        if datatype == "UINT8":
            return (
                f"uint8_h_div{format(divider, 'g').replace('.', 'p')}"
                if divider != 1
                else "uint8_h"
            )

    if (unit_lower == "min" or unit_lower == "minute") and datatype == "UINT16":
        return "uint16_min_div120"

    # RPM
    if unit_lower == "rpm":
        if datatype == "UINT16":
            return "uint16_rpm"
        if datatype == "INT16":
            return "int16_rpm"
        if datatype == "UINT8":
            return "uint8_rpm"
        if datatype == "FLOAT32":
            return "float32_rpm"

    # Minutes
    if unit_lower in ("min", "minute"):
        if divider == 1:
            if datatype == "UINT8":
                return "uint8_min"
            if datatype == "UINT32":
                return "uint32_min"
            if datatype == "UINT16":
                return "uint16_min"
        if datatype == "UINT8" and divider == 5:
            return "uint8_min_div5"

    # Seconds
    if unit_lower in ("s", "sec", "second", "seconds"):
        if datatype == "UINT8":
            return f"uint8_s_div{format(divider, 'g').replace('.', 'p')}" if divider != 1 else "uint8_s"
        if datatype == "UINT16":
            return f"uint16_s_div{format(divider, 'g').replace('.', 'p')}" if divider != 1 else "uint16_s"
        if datatype == "UINT32":
            return f"uint32_s_div{format(divider, 'g').replace('.', 'p')}" if divider != 1 else "uint32_s"

    # Kelvin
    if unit_lower == "k" and datatype.startswith(("DATA", "INT", "UINT", "FLOAT")):
        name = f"{datatype.lower()}_kelvin"
        if divider != 1:
            name += f"_div{format(divider, 'g').replace('.', 'p')}"
        return name

    unit_profile_base = UNIT_PROFILE_BASES.get((datatype, unit_lower))
    if unit_profile_base:
        if divider != 1:
            return (
                f"{unit_profile_base}_div"
                f"{format(divider, 'g').replace('.', 'p')}"
            )
        return unit_profile_base

    # Basic type fallback
    basic_map = {
        "DATA2C": "data2c",
        "DATA2B": "data2b",
        "DATA1C": "data1c",
        "DATA1B": "data1b",
        "UINT8": "uint8",
        "UINT16": "uint16",
        "UINT24": "uint24",
        "UINT32": "uint32",
        "INT8": "int8",
        "INT16": "int16",
        "INT24": "int24",
        "INT32": "int32",
        "FLOAT32": "float32",
        "UINT16R": "uint16r",
        "UINT24R": "uint24r",
        "INT16R": "int16r",
        "INT24R": "int24r",
        "UINT32R": "uint32r",
        "INT32R": "int32r",
        "FLOAT32R": "float32r",
        "BCD8": "bcd8",
        "BCD16": "bcd16",
        "BCD24": "bcd24",
        "BCD32": "bcd32",
        "BOOL": "bool",
        "DATA2BR": "data2br",
        "DATA2CR": "data2cr",
        "CHAR1": "char1",
        "CHAR2": "char2",
        "CHAR3": "char3",
        "CHAR4": "char4",
        "CHAR5": "char5",
        "CHAR6": "char6",
        "CHAR7": "char7",
        "CHAR8": "char8",
        "CHAR9": "char9",
        "CHAR10": "char10",
        "CHAR11": "char11",
        "CHAR12": "char12",
        "CHAR13": "char13",
        "CHAR14": "char14",
        "CHAR15": "char15",
        "CHAR16": "char16",
        "HEX1": "hex1",
        "HEX2": "hex2",
        "HEX3": "hex3",
        "HEX4": "hex4",
        "HEX5": "hex5",
        "HEX6": "hex6",
        "HEX7": "hex7",
        "HEX8": "hex8",
        "HEX9": "hex9",
        "HEX10": "hex10",
        "HEX11": "hex11",
        "HEX12": "hex12",
        "HEX13": "hex13",
        "HEX14": "hex14",
        "HEX15": "hex15",
        "HEX16": "hex16",
        "DATE_BCD4": "date_bcd4",
        "DATE_BCD3": "date_bcd3",
        "DATE_BCD4Z": "date_bcd4z",
        "DATE_BIN3": "date_bin3",
        "DATE_BIN4": "date_bin4",
        "DATE_DAY2": "date_day2",
        "DATETIME_MIN4": "datetime_min4",
        "TIME_BCD3R": "time_bcd3r",
        "TIME_BCD2R": "time_bcd2r",
        "TIME_BIN3R": "time_bin3r",
        "TIME_BIN3": "time_bin3",
        "TIME_BIN2R": "time_bin2r",
        "TIME_BIN2": "time_bin2",
        "TIME_MIN2": "time_min2",
        "TIME_TRUNC10": "time_trunc10",
        "TIME_TRUNC15": "time_trunc15",
        "TIME_TRUNC30": "time_trunc30",
        "PIN2": "pin2",
        "TEM_P": "tem_p",
    }
    return basic_map.get(datatype, "uint8")


def _parse_factor(args_str: str | None) -> float | None:
    """Parse a numeric factor/divisor argument."""
    if not args_str:
        return None
    try:
        return float(args_str.strip())
    except ValueError:
        return None


def _profile_number(value: Any, default: int = 0) -> int | float:
    """Normalize numeric profile metadata for identity and JSON output."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value) if isinstance(value, float) and value.is_integer() else value
    text = str(value).strip()
    try:
        if re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", text):
            return int(text, 16)
        try:
            return int(text, 10)
        except ValueError:
            number = float(text)
            return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return default


HA_SENSOR_UNIT_PROFILES: dict[str, str] = {
    "°c": "sensor_temperature",
    "c": "sensor_temperature",
    "celsius": "sensor_temperature",
    "k": "sensor_temperature",
    "bar": "sensor_pressure",
    "mbar": "sensor_pressure",
    "pa": "sensor_pressure",
    "hpa": "sensor_pressure",
    "kpa": "sensor_pressure",
    "l/min": "sensor_flow",
    "lpm": "sensor_flow",
    "l/h": "sensor_flow",
    "m3/h": "sensor_flow",
    "m³/h": "sensor_flow",
    "l/s": "sensor_flow",
    "w": "sensor_power",
    "kw": "sensor_power",
    "wh": "sensor_energy",
    "kwh": "sensor_energy",
    "mwh": "sensor_energy",
    "v": "sensor_voltage",
    "mv": "sensor_voltage",
    "a": "sensor_current",
    "ma": "sensor_current",
    "hz": "sensor_frequency",
    "khz": "sensor_frequency",
    "dbm": "sensor_rssi",
}

_BOOLEAN_ON_LABELS = {
    "active",
    "enabled",
    "open",
    "on",
    "present",
    "running",
    "true",
    "yes",
}
_BOOLEAN_OFF_LABELS = {
    "close",
    "closed",
    "disabled",
    "false",
    "inactive",
    "missing",
    "off",
    "no",
    "stopped",
}


def _is_binary_enum(meta: dict[str, Any]) -> bool:
    entries = meta.get("values", [])
    if not isinstance(entries, list) or len(entries) != 2:
        return False

    states: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return False
        label = re.sub(r"[^a-z]", "", str(entry.get("key", "")).lower())
        if label not in _BOOLEAN_ON_LABELS and label not in _BOOLEAN_OFF_LABELS:
            return False
        value = entry.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        states[label] = value

    on_values = [
        value for label, value in states.items() if label in _BOOLEAN_ON_LABELS
    ]
    off_values = [
        value for label, value in states.items() if label in _BOOLEAN_OFF_LABELS
    ]
    return (
        len(on_values) == len(off_values) == 1
        and on_values[0] == 1
        and off_values[0] == 0
    )


def _semantic_ha_profile(field: FieldIR, rw: str, command_name: str = "") -> str:
    """Choose a known HA profile only when the field semantics are clear."""
    meta = field.meta or {}
    if meta.get("bits"):
        return "binary_sensor"

    if _is_binary_enum(meta):
        if rw == "write":
            return "switch"
        if rw == "read":
            return "binary_sensor"

    if rw != "read":
        return ""

    unit = (field.unit or meta.get("unit") or "").strip().lower()
    semantic_name = re.sub(
        r"([a-z0-9])([A-Z])", r"\1 \2", f"{command_name} {field.name}"
    )
    name_tokens = set(re.findall(r"[a-z0-9]+", semantic_name.lower()))
    if unit in ("%", "percent"):
        if "rh" in name_tokens or any(
            "humid" in token for token in name_tokens
        ):
            return "sensor_humidity"
        return ""

    profile = HA_SENSOR_UNIT_PROFILES.get(unit)
    if profile:
        return profile

    if name_tokens & {"sum", "total"}:
        return "sensor_total"
    return ""


def _profile_signature(field: FieldIR) -> tuple[Any, ...]:
    """Identify a profile by all properties represented in data_profiles."""
    meta = field.meta or {}
    datatype = field.our_datatype or _map_type(
        field.ebus_type, _max_length_from_meta(meta)
    )
    unit = field.unit or meta.get("unit", "") or ""
    factor = field.factor or meta.get("factor") or meta.get("divisor")
    divider = _parse_factor(str(factor)) if factor not in (None, "") else None
    if divider is None:
        divider = 1.0
    try:
        digits = int(meta.get("digits", 0) or 0)
    except (TypeError, ValueError):
        digits = 0
    return (
        datatype,
        unit,
        divider,
        digits,
        _profile_number(meta.get("min")),
        _profile_number(meta.get("max")),
    )


def _profile_names_for_family(fam: FamilyIR) -> dict[tuple[Any, ...], str]:
    """Return deterministic profile names shared by profile and command output."""
    names: dict[tuple[Any, ...], str] = {}
    used_names: set = set()
    for command in fam.commands:
        for field in command.fields:
            signature = _profile_signature(field)
            if signature in names or signature[0] not in SUPPORTED_DATATYPES:
                continue
            profile_name = _map_profile_name(
                field.ebus_type,
                signature[1],
                _max_length_from_meta(field.meta),
                signature[2],
            )
            original_name = profile_name
            suffix = 1
            while profile_name in used_names:
                profile_name = f"{original_name}_{suffix}"
                suffix += 1
            names[signature] = profile_name
            used_names.add(profile_name)
    return names


def _max_length_from_meta(meta: dict[str, Any] | None) -> int | None:
    """Parse @maxLength from field/scalar metadata (stored as a string)."""
    if not meta:
        return None
    v = meta.get("max_length")
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _decorator_meta(decorators: list[dict[str, Any]]) -> dict[str, Any]:
    """Metadata contributed by a field's decorators.

    Shared by register fields and composite (plain-model) children so both
    paths interpret `@constValue`, `@maxLength`, `@minValue`, ... alike.
    """
    meta: dict[str, Any] = {}
    for dec in decorators:
        name = dec.get("name", "")
        args = dec.get("args") or []
        if name == "unit" and args:
            meta["unit"] = args[0].strip('"').strip("'")
        elif name in ("factor", "divisor") and args:
            meta["factor"] = args[0]
        elif name == "step" and args:
            s = args[0].strip()
            try:
                float(s)
                meta["digits"] = len(s.split(".")[1].rstrip("0")) if "." in s else 0
            except ValueError:
                pass
        elif name in ("minValue", "maxValue") and args:
            key = "min" if name == "minValue" else "max"
            try:
                meta[key] = int(args[0])
            except ValueError:
                try:
                    meta[key] = float(args[0])
                except ValueError:
                    pass
        elif name == "constValue" and args:
            meta["const_value"] = args[0]
        elif name == "maxLength" and args:
            meta["max_length"] = args[0]
        elif name in ("in", "out"):
            previous = meta.get("direction")
            direction = name
            if previous not in (None, direction):
                meta["direction_conflict"] = True
            else:
                meta["direction"] = direction
            if args:
                value = args[0].strip().lower()
                if value in ("true", "false"):
                    meta["write_only"] = value == "true"
                else:
                    meta["direction_conflict"] = True
    return meta


def _field_included_for_direction(field: FieldIR, rw: str) -> bool:
    """Apply @in/@out and writeOnly field inclusion for a command side."""
    meta = field.meta or {}
    if meta.get("direction_conflict"):
        return False

    write_only = meta.get("write_only")
    if write_only is not None:
        return (rw == "write") if write_only else (rw == "read")

    direction = meta.get("direction")
    if direction == "in":
        return rw == "read"
    if direction == "out":
        return rw == "write"
    return True


def _const_wire_hex(field: FieldIR) -> str:
    """Render a field's @constValue as its wire bytes (lowercase hex).

    HEX fields carry their literal bytes; numeric and char types are packed
    with the datatype width and endianness. Returns "" when the field has no
    const or the literal cannot be interpreted.
    """
    raw = (field.meta or {}).get("const_value")
    if raw is None or str(raw).strip() == "":
        return ""
    text = str(raw).strip().strip('"').strip("'")
    datatype = field.our_datatype or ""
    if datatype.startswith("HEX"):
        return text.lower()
    size = DATATYPE_SIZE.get(datatype)
    try:
        number = int(text, 16) if re.match(r"^[+-]?0[xX]", text) else int(text, 10)
    except ValueError:
        return text.lower()
    if not size:
        return text.lower()
    number &= (1 << (size * 8)) - 1
    order = "big" if datatype.endswith("R") else "little"
    return number.to_bytes(size, order).hex()


def _format_command_name(model_name: str, namespace: str = "") -> str:
    """Format a command name from model name and namespace.

    Emits the upstream TypeSpec model name verbatim (PascalCase, e.g.
    ``CompHoursHwc``, ``Setpoints_Monday``) — no snake_case conversion, no
    namespace prefix, no slash hierarchy. This matches the ebusd-configuration
    CSV ``name`` column exactly, so regenerated output diffs cleanly against
    upstream. The runtime passes the name through untouched
    (``mqtt.cpp`` values topic, ``mqtt_ha.cpp`` state topic); the slash-based
    grouping seen in hand-written ``config/*.json`` is a human-authored
    convention and is not reproduced by the generator.
    """
    return model_name


def tsp_type_to_datatype(tsp_type: str) -> str:
    """Map TypeSpec/tsp type to our datatype."""
    return _map_type(tsp_type)


def profiles_to_flat_entries(fam: FamilyIR, log: Any = None) -> list[dict[str, Any]]:
    """Convert FamilyIR commands to flat data_profiles.json schema entries.

    Each unique field profile becomes one flat entry:
    {name, datatype, unit, divider, digits, min, max}

    Entries are named canonically via _map_profile_name so that command
    field references (which use the same mapping) resolve to existing
    profiles. Deduplication includes datatype, unit, divider, digits, and
    min/max so fields with different profile metadata remain distinct.
    """
    log = log if log is not None else NULL_LOG
    entries: list[dict[str, Any]] = []
    profile_names = _profile_names_for_family(fam)
    seen: set = set()

    for cmd in fam.commands:
        for f in cmd.fields:
            signature = _profile_signature(f)
            datatype, unit, divider, digits, min_val, max_val = signature

            # Skip datatypes the ebus-library cannot decode/encode.
            # (e.g. CHAR17+, HEX17+, ERRORHISTORY, POWER, etc.)
            if datatype not in SUPPORTED_DATATYPES:
                log.warning(
                    "profile",
                    "profile entry skipped: datatype not supported by ebus-library",
                    action="skipped_unsupported_datatype",
                    name=f.name,
                    input_type=f.ebus_type,
                    datatype=datatype,
                    classification=_classify_type(f.ebus_type, datatype),
                )
                continue

            if signature in seen:
                log.debug(
                    "profile",
                    "profile entry deduplicated",
                    action="deduplicated",
                    name=f.name,
                    datatype=datatype,
                    unit=unit,
                )
                continue
            seen.add(signature)

            profile_name = profile_names[signature]

            entry = {
                "name": profile_name,
                "datatype": datatype,
                "unit": unit,
                "divider": divider if divider != 1.0 else 1,
                "digits": digits,
                "min": min_val,
                "max": max_val,
            }
            entries.append(entry)

            log.info(
                "profile",
                "data profile entry emitted",
                action="emitted",
                name=profile_name,
                datatype=datatype,
                unit=unit,
                divider=entry["divider"],
                digits=digits,
                classification=_classify_type(f.ebus_type, datatype),
            )

    return entries


def commands_to_flat_entries(
    fam: FamilyIR,
    key_prefix: str = "",
    aliases: dict[str, str] | None = None,
    log: Any = None,
    default_zz: int | None = None,
) -> list[dict[str, Any]]:
    """Convert FamilyIR commands to config/simulation.json schema entries.

    {key, name, zz, pbsb, [dx], [nn], wpbsb, [wdx], interval, master,
     fields: [{name, profile, position, ha_profile, [bits]}]}

    Split addressing: the read id is pbsb + dx (write id = wpbsb + wdx);
    pbsb is always present (empty for write-only commands) while the dx/wdx
    tails appear only when they carry bytes. NN stays runtime-derived
    (len(d) + value), with nn only for wire quirks.
    """
    log = log if log is not None else NULL_LOG
    entries: list[dict[str, Any]] = []
    seen_read_id: dict[str, str] = {}
    profile_names = _profile_names_for_family(fam)

    # Try to get MF from aliases if not in meta
    default_mf = 0x00
    if aliases and "MF" in aliases:
        try:
            default_mf = int(aliases["MF"], 16)
        except ValueError:
            default_mf = 0x00

    for idx, c in enumerate(fam.commands, start=1):
        meta = c.meta or {}
        namespace = meta.get("namespace", "")

        # Get addressing from meta.
        # Command layout: ZZ + id, where id = PB SB D... (2..6 bytes).
        # The D tail comes from the parser-resolved read_tail/write_tail
        # (@base D bytes + inherited ancestors, never a fabricated 0x0d)
        # followed by the model's own @ext bytes.
        zz = meta.get("zz")
        if zz is None:
            zz = default_zz if default_zz is not None else 0x08
        if meta.get("write_to_source"):
            valid_source = {
                0x00, 0x01, 0x03, 0x07, 0x0f,
                0x10, 0x11, 0x13, 0x17, 0x1f,
                0x30, 0x31, 0x33, 0x37, 0x3f,
                0x70, 0x71, 0x73, 0x77, 0x7f,
                0xf0, 0xf1, 0xf3, 0xf7, 0xff,
            }
            if zz not in valid_source:
                source_zz = (zz - 5) & 0xff
                if source_zz in valid_source:
                    zz = source_zz
                else:
                    c.unsupported = True
                    c.unsupported_reason = (
                        f"@write(true) target zz={zz:02x} has no source address pendant"
                    )
        mf = meta.get("mf", default_mf)  # Default MF (PB byte, e.g. 0xb5)
        pb = meta.get("pb", 0x09)  # Default SB

        read_tail = meta.get("read_tail")
        write_tail = meta.get("write_tail")
        ext_bytes = list(meta.get("ext") or [])

        def _hex(bs: list[int]) -> str:
            return "".join(f"{b:02x}" for b in bs)

        # NN bytes: ZZ PB SB NN D... [data...]
        #   read  NN typically 0x03 (no data)
        #   write NN = 3 + sum of datatype sizes of the writable field(s).
        nn_read = meta.get("read_nn", 0x03)

        data_byte_count = 0
        if c.fields:
            for f in c.fields:
                dt = f.our_datatype or f.ebus_type.upper()
                if dt in SUPPORTED_DATATYPES:
                    data_byte_count += DATATYPE_SIZE.get(dt, 0)
        nn_write = meta.get("write_nn", 3 + data_byte_count)

        # Split schema: zz + pbsb/dx (read) / wpbsb/wdx (write); NN is
        # derived at the runtime from the dx length (plus the value length
        # for writes). The halves are empty when the command has no
        # read/write side (write-only commands carry wpbsb/wdx only).
        # The SB byte (pb) is per-direction: read and write parents may
        # use different PBSB (e.g. *r B504 19 / *w B505 2e).
        zz_hex = f"{zz:02x}"
        mf_hex = f"{mf:02x}"
        read_prefix = f"{mf_hex}{meta.get('read_pb', pb):02x}"
        write_prefix = f"{mf_hex}{meta.get('write_pb', pb):02x}"
        id_hex = (
            read_prefix + _hex(read_tail) + _hex(ext_bytes)
            if read_tail is not None
            else ""
        )
        wid_hex = (
            write_prefix + _hex(write_tail) + _hex(ext_bytes)
            if write_tail is not None
            else ""
        )
        # Explicit read NN only when it differs from the derived len(id)-2
        # and the command actually has a read side.
        nn_hex = f"{nn_read:02x}" if (nn_read != 3 and id_hex) else ""

        if c.rw == "write" and "write_nn" not in meta:
            log.debug(
                "command",
                "write NN computed from datatype size",
                action="write_cmd_nn_from_datatype",
                name=c.name,
                key=f"{idx:03d}",
                namespace=namespace,
                nn_write=nn_write,
                data_byte_count=data_byte_count,
                fields=[(f.name, f.our_datatype or f.ebus_type) for f in c.fields],
            )

        log.debug(
            "command",
            "write id generated" if wid_hex else "no write command (read-only)",
            action="write_cmd_generated" if wid_hex else "read_only",
            name=c.name,
            zz=zz_hex,
            id=id_hex,
            wid=wid_hex,
            rw=c.rw,
        )

        # Determine key
        # Use sequential numbering with 3-digit zero-padding by default
        # This matches the working commands.json format ("01", "02", etc.)
        key = f"{idx:03d}"

        # Override with prefix if provided
        if key_prefix:
            key = f"{key_prefix}{key}"

        # Build fields with 1-based byte positions: position = 1 + cumulative
        # byte offset of preceding datatype sizes (firmware uses
        # field_pos = position - 1 to index into the data part).
        fields: list[dict[str, Any]] = []
        byte_offset = 0
        for f in c.fields:
            signature = _profile_signature(f)
            profile = profile_names.get(signature)
            if profile is None:
                profile = _map_profile_name(
                    f.ebus_type,
                    signature[1],
                    _max_length_from_meta(f.meta),
                    signature[2],
                )

            # Get min/max overrides from field meta
            min_val = f.meta.get("min") if f.meta.get("min") is not None else None
            max_val = f.meta.get("max") if f.meta.get("max") is not None else None

            field_entry = {
                "name": f.name,
                "profile": profile,
                "position": byte_offset + 1,
                "ha_profile": _semantic_ha_profile(f, c.rw, c.name),
            }

            # Add min/max if present
            if min_val is not None:
                field_entry["min"] = min_val
            if max_val is not None:
                field_entry["max"] = max_val
            if f.meta.get("bits"):
                field_entry["bits"] = f.meta["bits"]
            const_hex = _const_wire_hex(f)
            if const_hex:
                field_entry["const"] = const_hex
                log.info(
                    "command",
                    "command field const emitted",
                    action="const_field_emitted",
                    name=f.name,
                    input_type=f.ebus_type,
                    datatype=f.our_datatype or "",
                    const=const_hex,
                )

            fields.append(field_entry)

            datatype = f.our_datatype or _map_type(
                f.ebus_type, _max_length_from_meta(f.meta)
            )
            if datatype in DATATYPE_SIZE:
                byte_offset += DATATYPE_SIZE[datatype]
            else:
                log.warning(
                    "command",
                    "datatype size unknown; positions after this field may be wrong",
                    action="unknown_datatype_size",
                    name=f.name,
                    input_type=f.ebus_type,
                    datatype=datatype,
                )
            log.debug(
                "profile",
                "command field profile selected",
                action="profile_selected",
                name=f.name,
                input_type=f.ebus_type,
                datatype=f.our_datatype
                or _map_type(f.ebus_type, _max_length_from_meta(f.meta)),
                unit=f.unit or "",
                profile=profile,
                classification=_classify_type(
                    f.ebus_type,
                    f.our_datatype
                    or _map_type(f.ebus_type, _max_length_from_meta(f.meta)),
                ),
            )

        command_name = _format_command_name(c.name, namespace)
        # Split schema keys: read id = pbsb + dx, write id = wpbsb + wdx.
        # id_hex/wid_hex are always PB SB + tail (>= 4 hex chars) when set.
        entry: dict[str, Any] = {
            "key": key,
            "name": command_name,
            "zz": zz_hex,
            "pbsb": id_hex[:4] if id_hex else "",
        }
        if len(id_hex) > 4:
            entry["dx"] = id_hex[4:]
        if nn_hex:
            entry["nn"] = nn_hex
        if wid_hex:
            entry["wpbsb"] = wid_hex[:4]
            if len(wid_hex) > 4:
                entry["wdx"] = wid_hex[4:]
        entry["interval"] = 0  # Default to passive only
        entry["master"] = False  # Default
        entry["fields"] = fields

        # Deduplicate namespace collisions: same model in multiple namespaces
        # produces identical zz+id + fields. Keep all variants but log them
        # so the user can curate by hardware/software version. Write-only
        # commands carry no id, so fall back to wid for the key.
        read_key = zz_hex + (id_hex or wid_hex)
        duplicate = seen_read_id.get(read_key)
        if duplicate is not None:
            log.debug(
                "command",
                "namespace collision: same zz+id in another variant",
                action="namespace_collision",
                key=key,
                name=command_name,
                namespace=namespace,
                zz=zz_hex,
                id=id_hex,
                wid=wid_hex,
                collides_with=duplicate,
            )
        else:
            seen_read_id[read_key] = key
        entries.append(entry)

        log.info(
            "command",
            "command entry emitted",
            action="emitted",
            key=key,
            name=command_name,
            namespace=namespace,
            zz=zz_hex,
            id=id_hex,
            wid=wid_hex,
            rw=c.rw,
            fields=len(fields),
        )

    return entries


def build_profiles_and_commands(
    raw: dict[str, Any], manufacturer: int = 0x00, log: Any = None
) -> FamilyIR:
    """Build FamilyIR from raw tsp parser IR.

    Converts parser-extracted registers (commands) and fields into
    FamilyIR with ProfileIR grouping and CommandIR entries.
    """
    log = log if log is not None else NULL_LOG
    fam = FamilyIR()

    registers: list[dict[str, Any]] = raw.get("registers", [])
    enums: dict[str, Any] = raw.get("enums", {})
    scalars: dict[str, Any] = raw.get("scalars", {})
    aliases: dict[str, Any] = raw.get("aliases", {})
    models: dict[str, Any] = raw.get("models", {})

    # Identify base models that are only used for inheritance
    # These are models that appear in other models' @inherit decorators
    inherited_model_names: set = set()
    for reg in registers:
        inherit_list = reg.get("inherit") or []
        for parent_name in inherit_list:
            inherited_model_names.add(parent_name)

    # Build a namespace context from the file structure
    # For now, we'll extract it from the register meta if available

    # Resolve scalar aliases and types: if a field type is an alias or scalar,
    # follow to the base type and collect metadata
    def resolve_type_and_meta(t: str) -> tuple[str, dict[str, Any]]:
        """Resolve a type to its base type and collect metadata (unit, min, max, etc.)"""
        t_orig = t
        t = _strip_qualified(t)
        visited: set[str] = set()
        meta: dict[str, Any] = {}

        # Follow alias chain
        while t in aliases and t not in visited:
            visited.add(t)
            alias_val = aliases[t]
            # Check if alias has metadata
            if alias_val in scalars:
                scalar = scalars[alias_val]
                meta.update(scalar.get("meta", {}))
                t = _strip_qualified(scalar.get("base_type", ""))
            else:
                t = _strip_qualified(alias_val)

        # Follow scalar chain
        while t in scalars and t not in visited:
            visited.add(t)
            scalar = scalars[t]
            if scalar.get("unit"):
                meta["unit"] = scalar["unit"]
            if scalar.get("factor"):
                meta["factor"] = scalar["factor"]
            if scalar.get("digits"):
                meta["digits"] = scalar["digits"]
            if scalar.get("min") is not None:
                meta["min"] = scalar["min"]
            if scalar.get("max") is not None:
                meta["max"] = scalar["max"]
            if scalar.get("values_enum"):
                meta["values_enum"] = scalar["values_enum"]
            if scalar.get("max_length"):
                meta["max_length"] = scalar["max_length"]

            t = _strip_qualified(scalar.get("base_type", ""))

        enum_name = meta.get("values_enum")
        if isinstance(enum_name, str) and enum_name in enums:
            meta["values"] = enums[enum_name].get("entries", [])

        # Check if it's an enum
        if t in enums:
            meta["values_enum"] = t
            meta["values"] = enums[t].get("entries", [])

        datatype = _map_type(t)
        classification = _classify_type(t, datatype, enums)
        if classification == "defaulted":
            log.warning(
                "resolve",
                "type has no TypeSpec→library mapping; using raw name",
                action="defaulted",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
            )
        elif classification == "unsupported":
            log.warning(
                "resolve",
                "type has no native ebus-library DataType equivalent",
                action="unsupported",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
            )
        else:
            log.debug(
                "resolve",
                "type resolved",
                action="resolved",
                input_type=t_orig,
                resolved_type=t,
                datatype=datatype,
                classification=classification,
                unit=meta.get("unit", ""),
            )
        return t, meta

    def _lookup_model(
        type_name: str, namespace: str | None = None
    ) -> dict[str, Any]:
        """Look up a model by name, preferring namespace-qualified keys.

        With the fix for namespace collisions, models are stored with qualified
        keys like "Ochsner.command" or "Tem.command". This helper tries to find
        the most appropriate model by:
        1. If namespace is provided, try "{namespace}.{type_name}" first
        2. Try namespace prefixes (e.g., if namespace is "Ochsner._22102", also try "Ochsner")
        3. Fall back to unqualified type_name (for backward compatibility)
        4. Return empty dict if not found
        """
        if namespace:
            # Try the full qualified name first
            qualified_key = f"{namespace}.{type_name}"
            if qualified_key in models:
                return models[qualified_key]

            # Try namespace prefixes (e.g., "Ochsner._22102" -> try "Ochsner")
            # This handles the case where a model is defined in a parent namespace
            # but referenced from a child namespace
            parts = namespace.split(".")
            for i in range(len(parts) - 1, 0, -1):
                parent_ns = ".".join(parts[:i])
                qualified_key = f"{parent_ns}.{type_name}"
                if qualified_key in models:
                    return models[qualified_key]

        # Fall back to unqualified name (for models without namespace or
        # backward compatibility)
        if type_name in models:
            return models[type_name]
        return {}

    def expand_composite_field(
        parent_name: str,
        type_name: str,
        path: list[str],
        depth: int,
        namespace: str | None = None,
    ) -> list[FieldIR]:
        """Expand a composite (plain-model) field into leaf FieldIRs.

        Leaf names are the full field-name path joined with '_' prefixed by
        the parent field name, with repeated underscores collapsed:
        value: timer -> value_slot1_slot_from, value_daysel. Leaves resolve
        through the normal type machinery, so profiles, write NN, and byte
        positions follow automatically.
        """
        if depth > 8:
            log.warning(
                "template",
                "composite expansion depth exceeded",
                action="expansion_depth_exceeded",
                name=parent_name,
                input_type=type_name,
            )
            return []
        leaves: list[FieldIR] = []
        model = _lookup_model(type_name, namespace)
        model_namespace = model.get("namespace", namespace)
        for child in model.get("fields", []):
            child_name = str(child.get("name", ""))
            child_type = _strip_qualified(str(child.get("type", "")))
            if (
                _lookup_model(child_type, model_namespace)
                and child_type not in TYPE_MAP
            ):
                leaves.extend(
                    expand_composite_field(
                        parent_name,
                        child_type,
                        path + [child_name],
                        depth + 1,
                        model_namespace,
                    )
                )
                continue
            resolved_type, type_meta = resolve_type_and_meta(child_type)
            merged_meta = {
                **type_meta,
                **_decorator_meta(child.get("decorators") or []),
            }
            if child.get("meta"):
                merged_meta.update(child["meta"])
            leaf_name = "_".join([parent_name] + path + [child_name])
            while "__" in leaf_name:
                leaf_name = leaf_name.replace("__", "_")
            factor_str = merged_meta.get("factor", merged_meta.get("divisor", ""))
            factor_val = _parse_factor(factor_str) if factor_str else None
            leaves.append(
                FieldIR(
                    name=leaf_name,
                    ebus_type=resolved_type or child_type,
                    unit=merged_meta.get("unit", ""),
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=resolved_type.startswith(("S", "s")),
                    big_endian="R" in resolved_type
                    or ("B" in resolved_type and "L" not in resolved_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=_map_type(
                        resolved_type or child_type,
                        _max_length_from_meta(merged_meta),
                    ),
                    meta=merged_meta,
                )
            )
        return leaves

    def _service_field_ir() -> FieldIR:
        """UINT8 service companion of two-field template instances."""
        return FieldIR(
            name="service",
            ebus_type="UCH",
            unit="",
            factor="",
            offset="",
            length=0,
            signed=False,
            big_endian=False,
            bitfield=False,
            bitpos=-1,
            bitlen=0,
            mask="",
            our_datatype="UINT8",
            meta={},
        )

    # Process each register into commands
    for reg in registers:
        reg_name = reg.get("name", "unnamed")
        reg_str = reg.get("register", "")
        rw = reg.get("rw", "read")
        meta = dict(reg.get("meta", {}))
        reg_fields = reg.get("fields", [])
        template_name = reg.get("template")
        template_type = reg.get("template_type")
        namespace = reg.get("namespace", "")

        # Store namespace in meta for later use
        if namespace:
            meta["namespace"] = namespace

        # Build FieldIR list from raw fields
        field_irs: list[FieldIR] = []

        if template_name and template_type and not reg_fields:
            # Composite template argument (e.g. Timer<timer>): expand into
            # positioned leaf sub-fields. Mapped arguments (e.g. phase) are
            # excluded by the TYPE_MAP gate; the service companion of
            # two-field templates is preserved.
            tt = _strip_qualified(template_type)
            composite_leaves: list[FieldIR] = []
            if _lookup_model(tt, namespace) and tt not in TYPE_MAP:
                composite_leaves = expand_composite_field("value", tt, [], 0, namespace)
            if composite_leaves:
                log.debug(
                    "template",
                    "composite field expanded",
                    action="composite_expanded",
                    name="value",
                    input_type=tt,
                    leaves=[fi.name for fi in composite_leaves],
                )
                field_irs.extend(composite_leaves)
                if template_name in _TWO_FIELD_TEMPLATES:
                    field_irs.append(_service_field_ir())
            # Handle template models
            elif template_name in _SINGLE_FIELD_TEMPLATES:
                # Single field template: the type is template_type
                resolved_type, type_meta = resolve_type_and_meta(template_type)

                f_ebus_type = resolved_type
                f_our_datatype = _map_type(
                    f_ebus_type, _max_length_from_meta(type_meta)
                )

                # Get unit from template_type metadata or scalar
                f_unit = type_meta.get("unit", "")

                # Parse factor
                factor_str = type_meta.get("factor", type_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None

                # Determine digits
                digits = type_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0

                # Create field IR for the value field
                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=f_unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s"))
                    or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type
                    or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)

            elif template_name in _TWO_FIELD_TEMPLATES:
                # Two field template: value + service
                resolved_type, type_meta = resolve_type_and_meta(template_type)

                # Value field
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(
                    f_ebus_type, _max_length_from_meta(type_meta)
                )
                f_unit = type_meta.get("unit", "")
                factor_str = type_meta.get("factor", type_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None
                digits = type_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0

                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=f_unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s"))
                    or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type
                    or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)

                # Service field (UINT8)
                field_irs.append(_service_field_ir())
            else:
                # Unknown template: assume single value field
                resolved_type, type_meta = resolve_type_and_meta(template_type)
                f_ebus_type = resolved_type
                f_our_datatype = _map_type(
                    f_ebus_type, _max_length_from_meta(type_meta)
                )

                field_ir = FieldIR(
                    name="value",
                    ebus_type=f_ebus_type,
                    unit=type_meta.get("unit", ""),
                    factor=type_meta.get("factor", ""),
                    offset="",
                    length=0,
                    signed=f_ebus_type.startswith(("S", "s"))
                    or f_our_datatype.startswith("INT"),
                    big_endian="R" in f_ebus_type
                    or ("B" in f_ebus_type and "L" not in f_ebus_type),
                    bitfield=False,
                    bitpos=-1,
                    bitlen=0,
                    mask="",
                    our_datatype=f_our_datatype,
                    meta=type_meta,
                )
                field_irs.append(field_ir)
        else:
            # Regular model with explicit fields. A template definition
            # (template_type set, no instantiating model) only holds
            # unresolved placeholder fields (e.g. `value: T;`); it never
            # becomes a command and its fields are discarded below, so
            # resolve nothing and keep the placeholders from warning.
            if template_name is None and template_type is not None:
                reg_fields = []
            for f in reg_fields:
                f_name = f.get("name", "")
                f_ebus_type = f.get("ebus_type", "")
                f_decorators = f.get("decorators", [])
                f_meta = f.get("meta", {})

                # Composite field: plain model without a library mapping of
                # its own (mapped types like phase are never expanded) →
                # emit positioned leaf sub-fields instead of the raw type.
                leaf_type = _strip_qualified(f_ebus_type)
                if _lookup_model(leaf_type, namespace) and leaf_type not in TYPE_MAP:
                    leaves = expand_composite_field(f_name, leaf_type, [], 0, namespace)
                    if leaves:
                        log.debug(
                            "template",
                            "composite field expanded",
                            action="composite_expanded",
                            name=f_name,
                            input_type=leaf_type,
                            leaves=[fi.name for fi in leaves],
                        )
                        field_irs.extend(leaves)
                        continue

                # Resolve the type and get metadata
                resolved_type, type_meta = resolve_type_and_meta(f_ebus_type)

                # Merge metadata
                merged_meta = {**type_meta, **f_meta}
                if f.get("unit"):
                    merged_meta["unit"] = f["unit"]
                if f.get("factor"):
                    merged_meta["factor"] = f["factor"]

                # Field decorators contribute metadata (const, maxLength,
                # unit, limits); shared with composite expansion.
                merged_meta.update(_decorator_meta(f_decorators))

                # Determine signedness
                signed = resolved_type.startswith(("S", "s"))

                # Determine endianness
                big_endian = "R" in resolved_type or (
                    "B" in resolved_type and "L" not in resolved_type
                )

                # Bitfield info
                bitfield = f.get("bitfield", False)
                bitpos = f.get("bitpos", -1)
                bitlen = f.get("bitlen", 0)
                mask = f.get("mask", "")

                # Get factor from merged metadata
                factor_str = merged_meta.get("factor", merged_meta.get("divisor", ""))
                factor_val = _parse_factor(factor_str) if factor_str else None

                # Get unit from merged metadata
                unit = merged_meta.get("unit", "")

                # Get digits
                digits = merged_meta.get("digits", 0)
                if isinstance(digits, str):
                    try:
                        digits = int(digits)
                    except ValueError:
                        digits = 0

                field_ir = FieldIR(
                    name=f_name,
                    ebus_type=resolved_type or f_ebus_type,
                    unit=unit,
                    factor=str(factor_val) if factor_val is not None else "",
                    offset="",
                    length=0,
                    signed=signed,
                    big_endian=big_endian,
                    bitfield=bitfield,
                    bitpos=bitpos,
                    bitlen=bitlen,
                    mask=mask,
                    our_datatype=_map_type(
                        resolved_type or f_ebus_type, _max_length_from_meta(merged_meta)
                    ),
                    meta=merged_meta,
                )
                field_irs.append(field_ir)

        # Determine the command's direction from the parser-resolved id
        # tails: a write side exists when write_tail was seeded/inherited,
        # a read side when read_tail was. Decorator/template rules only
        # remain as a fallback for registers with no resolved sides.
        read_tail = meta.get("read_tail")
        write_tail = meta.get("write_tail")
        if write_tail is not None:
            rw = "write"
        elif read_tail is not None:
            rw = "read"
        else:
            rw = reg.get("rw", "read")

        before_filter = list(field_irs)
        field_irs = [
            f
            for f in before_filter
            if _field_included_for_direction(f, rw)
        ]
        conflicts = [
            f.name for f in before_filter
            if (f.meta or {}).get("direction_conflict")
        ]
        for f in before_filter:
            if f not in field_irs:
                log.debug(
                    "command",
                    "field excluded by direction decorator",
                    action="field_direction_excluded",
                    name=reg_name,
                    field=f.name,
                    rw=rw,
                    direction=(f.meta or {}).get("direction", ""),
                    write_only=(f.meta or {}).get("write_only"),
                )
        if conflicts:
            log.warning(
                "command",
                "conflicting @in/@out field decorators",
                action="direction_conflict",
                name=reg_name,
                fields=conflicts,
            )

        unsupported = False
        unsupported_reason = ""

        if reg.get("unsupported"):
            unsupported = True
            unsupported_reason = reg.get("unsupported_reason", "unsupported register")
        if conflicts:
            unsupported = True
            unsupported_reason = "conflicting @in/@out field decorators"

        if rw not in ("read", "write"):
            unsupported = True
            unsupported_reason = f"unknown rw direction: {rw}"

        # BI bitfield children (BI0..BI7) share one wire byte: collapse each
        # consecutive run into a single UINT8 field with a `bits` name->bit
        # map first; anything still gated (boolean/BOOL, raw bitfield names)
        # drops the whole command.
        field_irs = _merge_bit_runs(field_irs)
        for f in field_irs:
            if f.ebus_type in _BIT_GATED_EBUS_TYPES:
                unsupported = True
                unsupported_reason = (
                    f"BI bitfield field {f.name!r} (type {f.ebus_type!r})"
                )
                break

        writable = rw == "write"
        log.debug(
            "command",
            "writability determined",
            action="writable" if writable else "read_only",
            name=reg_name,
            namespace=reg.get("namespace", ""),
            rw=rw,
            template=template_name,
            explicit_write=bool(meta.get("explicit_write")),
            explicit_passive=bool(meta.get("explicit_passive")),
        )

        cmd_ir = CommandIR(
            name=reg_name,
            profile_key=None,
            register=reg_str,
            rw=rw,
            fields=field_irs,
            unsupported=unsupported,
            unsupported_reason=unsupported_reason,
            meta=meta,
        )
        # Determine kind of register
        if template_name is None and template_type is not None:
            kind = "template_definition"
        elif reg_name in inherited_model_names:
            kind = "inherited_base"
        else:
            kind = "register"

        # Only concrete registers become commands; skip template definitions,
        # inherited base models, and registers the merge/BI gate marked
        # unsupported (no id/wid side or bitfield payload).
        if kind == "register" and not unsupported:
            fam.commands.append(cmd_ir)

        # Log what happened to this register.
        if kind == "register" and unsupported:
            log.warning(
                "command",
                "register skipped: unsupported",
                action="skipped_unsupported",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                cause=unsupported_reason,
            )
        elif kind == "template_definition":
            log.warning(
                "command",
                "template definition skipped (only instantiations become commands)",
                action="skipped_template_definition",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
            )
        elif kind == "inherited_base":
            log.warning(
                "command",
                "register skipped because it is referenced via @inherit",
                action="skipped",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                cause="inherited_base_model",
            )
        else:
            log.debug(
                "command",
                "register converted to command",
                action="converted",
                name=reg_name,
                namespace=reg.get("namespace", ""),
                kind=kind,
                fields=len(field_irs),
            )

    # Group commands into profiles by canonical field semantics
    _group_profiles(fam)

    return fam


def _group_profiles(fam: FamilyIR) -> None:
    """Group commands into profiles by canonical field semantics.

    Groups by: datatype + unit + scaling + signedness + endianness.
    Each group becomes a ProfileIR; commands reference it via profile_key.
    """
    groups: dict[str, list[CommandIR]] = {}

    for cmd in fam.commands:
        if not cmd.fields:
            key = "no_fields"
        else:
            # Derive profile key from first field's semantics
            f = cmd.fields[0]
            key_parts = [
                f.our_datatype or f.ebus_type or "x",
                f.unit or "",
                f.factor or "",
                "s" if f.signed else "u",
                "be" if f.big_endian else "le",
            ]
            key = "_".join(p for p in key_parts if p)
            if len(key) > 24:
                key = key[:24].rstrip("_")

        if key not in groups:
            groups[key] = []
        groups[key].append(cmd)

    # Build ProfileIRs and assign profile_key to commands
    for key, cmds in groups.items():
        # Collect all unique fields from commands in this group
        seen_fields: dict[str, FieldIR] = {}
        for cmd in cmds:
            for f in cmd.fields:
                if f.name not in seen_fields:
                    seen_fields[f.name] = f

        profile_fields = list(seen_fields.values())
        profile_ir = ProfileIR(key=key, fields=profile_fields, meta={})
        fam.profiles[key] = profile_ir

        # Assign profile_key to commands in this group
        for cmd in cmds:
            cmd.profile_key = key
