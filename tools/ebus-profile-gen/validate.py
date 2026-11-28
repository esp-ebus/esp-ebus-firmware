"""Validate emitted structures against our constraints.

Validation is derived from two sources:

* the structured conversion log (:func:`validate_log`), which records every
  decision (type classification, profile selection, skips, collisions), and
* the emitted JSON entries (:func:`check_no_trailing_underscores`).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Mirror of COMMAND_MAX_FIELDS (platformio.ini): the firmware's per-command
# field table size and the schema's documented 1..13 range
# (doc/command-schema.md). Fieldless commands are a supported feature
# (whole-payload writes), so only the upper bound is enforced here.
MAX_FIELDS_PER_COMMAND = 13

UNSUPPORTED_TYPESPEC = "unsupported-typespec"
FIRMWARE_SCHEMA = "firmware-schema"
EMITTED_OUTPUT = "emitted-output"


def _issue(category: str, code: str, message: str) -> dict[str, str]:
    return {"category": category, "code": code, "message": message}


def format_issue(issue: dict[str, str]) -> str:
    return f"[{issue['category']}] {issue['message']}"


def check_no_trailing_underscores(obj: Any, path: str = "") -> list[str]:
    issues: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_"):
                issues.append(
                    f"[{EMITTED_OUTPUT}] trailing underscore in key: {path}.{k}"
                )
            issues.extend(
                check_no_trailing_underscores(v, f"{path}.{k}" if path else k)
            )
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues.extend(check_no_trailing_underscores(v, f"{path}[{i}]"))
    elif isinstance(obj, str) and obj.endswith("_"):
        issues.append(
            f"[{EMITTED_OUTPUT}] trailing underscore in string value at {path}"
        )
    return issues


def check_profile_keys_short(obj: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    profs = obj.get("profiles") or {}
    if isinstance(profs, dict):
        for k in profs:
            if len(k) > 24:
                issues.append(f"profile key too long (>24): {k}")
    return issues


def validate_log(
    records: Iterable[dict[str, Any]],
    profiles_entries: list[dict[str, Any]] | None = None,
    commands_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Turn conversion-log records into a list of human-readable issues.

    Any record that indicates the output is not ready to use becomes an issue:
    defaulted/unsupported type mappings, emitted template definitions, skipped
    inherited bases, and zz+id collisions. When profile and command entries
    are supplied, referenced profile names are cross-checked for existence.
    """
    issues = validate_log_entries(records, profiles_entries, commands_entries)
    return [format_issue(issue) for issue in issues]


def validate_log_entries(
    records: Iterable[dict[str, Any]],
    profiles_entries: list[dict[str, Any]] | None = None,
    commands_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Return structured validation failures with stable categories and codes."""
    issues: list[dict[str, str]] = []
    records = list(records)

    for rec in records:
        stage = rec.get("stage", "")
        reason = rec.get("reason", "")
        severity = rec.get("severity", "")

        if severity == "error":
            action = rec.get("action")
            category = (
                UNSUPPORTED_TYPESPEC
                if action in ("ambiguous_inherit_parent",)
                else EMITTED_OUTPUT
            )
            issues.append(_issue(category, "conversion-error", f"[{stage}] {reason}"))

        classification = rec.get("classification")
        if classification == "defaulted":
            issues.append(
                _issue(
                    UNSUPPORTED_TYPESPEC,
                    "defaulted-type",
                    f"[{stage}] defaulted type mapping: "
                    f"{rec.get('input_type')!r} -> {rec.get('datatype')!r}",
                )
            )
        elif classification == "unsupported":
            issues.append(
                _issue(
                    UNSUPPORTED_TYPESPEC,
                    "unsupported-type",
                    f"[{stage}] unsupported type (no native DataType): "
                    f"{rec.get('input_type')!r}",
                )
            )

        action = rec.get("action")
        if action == "emitted_template_definition":
            issues.append(
                _issue(
                    UNSUPPORTED_TYPESPEC,
                    "template-emitted",
                    f"[{stage}] template definition emitted as a command: "
                    f"{rec.get('name')!r}",
                )
            )
        if action in (
            "skipped_unsupported",
            "skipped_unsupported_datatype",
        ) or (
            action in ("unsupported", "defaulted")
            and classification not in ("unsupported", "defaulted")
        ):
            issues.append(
                _issue(
                    UNSUPPORTED_TYPESPEC,
                    action,
                    f"[{stage}] unsupported TypeSpec construct: "
                    f"{reason or rec.get('cause') or action}",
                )
            )

        if action == "emitted" and rec.get("rw") == "write" and not rec.get("wid"):
            issues.append(
                _issue(
                    FIRMWARE_SCHEMA,
                    "missing-wid",
                    f"[{stage}] writable command has no wid: {rec.get('name')!r}",
                )
            )

        if action == "emitted" and rec.get("zz") is not None:
            id_hex = rec.get("id", "")
            wid_hex = rec.get("wid", "")

            def _wid_ok(h: str) -> bool:
                return 4 <= len(h) <= 12 and len(h) % 2 == 0

            if not id_hex and not wid_hex:
                issues.append(
                    _issue(
                        FIRMWARE_SCHEMA,
                        "missing-id-wid",
                        f"[{stage}] command has neither id nor wid: "
                        f"{rec.get('name')!r}",
                    )
                )
            elif not id_hex:
                # Write-only command: id is empty by design, wid carries
                # the addressing and must obey the 2..6 byte rule.
                if not _wid_ok(wid_hex):
                    issues.append(
                        _issue(
                            FIRMWARE_SCHEMA,
                            "wid-length",
                            f"[{stage}] wid must be 2..6 bytes: "
                            f"{rec.get('name')!r} ({wid_hex!r})",
                        )
                    )
            elif not (4 <= len(id_hex) <= 12 and len(id_hex) % 2 == 0):
                issues.append(
                    _issue(
                        FIRMWARE_SCHEMA,
                        "id-length",
                        f"[{stage}] id must be 2..6 bytes: "
                        f"{rec.get('name')!r} ({id_hex!r})",
                    )
                )
            if wid_hex and not _wid_ok(wid_hex):
                issues.append(
                    _issue(
                        FIRMWARE_SCHEMA,
                        "wid-length",
                        f"[{stage}] wid must be 2..6 bytes: "
                        f"{rec.get('name')!r} ({wid_hex!r})",
                    )
                )

    if profiles_entries is not None and commands_entries is not None:
        known = {p.get("name") for p in profiles_entries}
        for cmd in commands_entries:
            field_count = len(cmd.get("fields", []))
            if field_count > MAX_FIELDS_PER_COMMAND:
                issues.append(
                    _issue(
                        FIRMWARE_SCHEMA,
                        "field-limit",
                        f"[command] {cmd.get('key')} has {field_count} fields "
                        f"(max {MAX_FIELDS_PER_COMMAND})",
                    )
                )
            for field in cmd.get("fields", []):
                const = field.get("const")
                # Fixed wire bytes: non-empty hex, even length,
                # at most the 16-byte data cap.
                if const is not None and (
                    not isinstance(const, str)
                    or not const
                    or len(const) > 32
                    or len(const) % 2 != 0
                    or any(c not in "0123456789abcdefABCDEF" for c in const)
                ):
                    issues.append(
                        _issue(
                            FIRMWARE_SCHEMA,
                            "invalid-const",
                            f"[command] {cmd.get('key')} field "
                            f"{field.get('name')!r} has invalid const {const!r}",
                        )
                    )
                profile = field.get("profile")
                if profile and profile not in known:
                    issues.append(
                        _issue(
                            EMITTED_OUTPUT,
                            "unknown-profile",
                            f"[command] {cmd.get('key')} field "
                            f"{field.get('name')!r} references unknown profile "
                            f"{profile!r}",
                        )
                    )

    return issues
