"""Verify corpus failure classes remain distinct and fail closed."""

import unittest

from validate import (
    FIRMWARE_SCHEMA,
    UNSUPPORTED_TYPESPEC,
    validate_log_entries,
)


class ValidationFailureTests(unittest.TestCase):
    def test_unsupported_typespec_construct_fails_closed(self):
        records = [
            {
                "stage": "resolve",
                "severity": "warn",
                "reason": "type has no native ebus-library DataType equivalent",
                "action": "unsupported",
                "classification": "unsupported",
                "input_type": "CHAR17",
            },
            {
                "stage": "command",
                "severity": "warn",
                "reason": "register skipped: unsupported",
                "action": "skipped_unsupported",
                "cause": "@chain constructs multiple IDs unsupported by firmware schema",
                "name": "Chained",
            },
        ]

        issues = validate_log_entries(records)

        self.assertTrue(issues)
        self.assertTrue(
            all(issue["category"] == UNSUPPORTED_TYPESPEC for issue in issues)
        )
        self.assertIn("unsupported-type", {issue["code"] for issue in issues})
        self.assertIn("skipped_unsupported", {issue["code"] for issue in issues})

    def test_firmware_id_limit_is_distinct_from_typespec_support(self):
        records = [
            {
                "stage": "command",
                "severity": "info",
                "reason": "command emitted",
                "action": "emitted",
                "zz": "08",
                "id": "b5",
                "wid": "",
                "name": "ShortId",
            }
        ]

        issues = validate_log_entries(records)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["category"], FIRMWARE_SCHEMA)
        self.assertEqual(issues[0]["code"], "id-length")

    def test_firmware_field_limit_is_a_schema_failure(self):
        fields = [{"name": f"field{i}", "profile": "uint8"} for i in range(14)]
        issues = validate_log_entries(
            [],
            profiles_entries=[{"name": "uint8"}],
            commands_entries=[{"key": "001", "fields": fields}],
        )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["category"], FIRMWARE_SCHEMA)
        self.assertEqual(issues[0]["code"], "field-limit")


if __name__ == "__main__":
    unittest.main()
