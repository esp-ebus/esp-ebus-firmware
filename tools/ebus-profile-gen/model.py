"""Internal IR for ebus-profile-gen."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldIR:
    name: str
    # hints from tsp files
    ebus_type: str = ""
    unit: str = ""
    factor: str = ""  # keep as string to preserve exactness if needed
    offset: str = ""
    length: int = 0
    signed: bool = False
    big_endian: bool = False
    bitfield: bool = False
    bitpos: int = -1
    bitlen: int = 0
    mask: str = ""
    # our target
    our_datatype: str = ""
    # extra
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandIR:
    name: str  # canonical command name
    profile_key: str | None = None
    register: str = ""
    rw: str = ""
    fields: list[FieldIR] = field(default_factory=list)  # inline if not grouped
    unsupported: bool = False
    unsupported_reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class FamilyIR:
    family: str = ""
    commands: list[CommandIR] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def profile_key_from_fields(fields: list[FieldIR]) -> str:
    """Derive a stable, short profile key from field semantics.

    TODO: refine grouping (datatype+scaling+unit+signed+endianness+bitfield).
    Keep FixedString-friendly (ProfileFS<24>).
    """
    parts = []
    for f in fields[:4]:  # keep short initially
        parts.append(f.our_datatype or f.ebus_type or "x")
    key = "_".join(parts) if parts else "profile"
    if len(key) > 24:
        key = key[:24].rstrip("_")
    return key
