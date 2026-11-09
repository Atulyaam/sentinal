"""Unit tests for Detection Rule Validation and Configuration Hashing."""
from __future__ import annotations

import unittest
from backend.detection.models import RuleDefinition
from backend.detection.rules import validate_rule_definition, compute_config_hash, get_builtin_rules


class TestRuleValidation(unittest.TestCase):
    """Test validation and hash generation for detection rules."""

    def test_valid_rule_definition(self) -> None:
        """A well-formed rule definition passes validation."""
        rule = RuleDefinition(
            rule_id="TEST-001",
            version="1.0.0",
            name="Test Rule",
            description="A valid test rule definition.",
            severity="Medium",
            enabled=True,
            config={"window_minutes": 10, "threshold": 5},
            limitations="None noted.",
        )
        validate_rule_definition(rule)
        self.assertEqual(rule.rule_id, "TEST-001")

    def test_builtin_rules_all_pass_validation(self) -> None:
        """All 5 built-in rules pass strict schema validation."""
        builtins = get_builtin_rules()
        self.assertEqual(len(builtins), 5)
        for rule in builtins:
            validate_rule_definition(rule)
            self.assertTrue(rule.rule_id)
            self.assertIn(rule.severity, ["Critical", "High", "Medium", "Low", "Info"])
            self.assertTrue(isinstance(rule.config, dict))

    def test_missing_or_empty_rule_id(self) -> None:
        """Rule definition with empty rule_id raises ValueError."""
        rule_dict = {
            "rule_id": "",
            "version": "1.0.0",
            "name": "No ID",
            "description": "desc",
            "severity": "Low",
            "enabled": True,
            "config": {},
            "limitations": "none",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_rule_definition(rule_dict)
        self.assertIn("rule_id", str(ctx.exception))

    def test_invalid_rule_id_format(self) -> None:
        """Rule definition with invalid characters in rule_id raises ValueError."""
        rule_dict = {
            "rule_id": "RULE 001!",
            "version": "1.0.0",
            "name": "Invalid ID Format",
            "description": "desc",
            "severity": "Low",
            "enabled": True,
            "config": {},
            "limitations": "none",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_rule_definition(rule_dict)
        self.assertIn("Invalid rule_id", str(ctx.exception))

    def test_invalid_severity(self) -> None:
        """Rule definition with invalid severity raises ValueError."""
        rule_dict = {
            "rule_id": "TEST-002",
            "version": "1.0.0",
            "name": "Bad Severity",
            "description": "desc",
            "severity": "urgent",  # Invalid
            "enabled": True,
            "config": {},
            "limitations": "none",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_rule_definition(rule_dict)
        self.assertIn("severity", str(ctx.exception).lower())

    def test_invalid_enabled_type(self) -> None:
        """Rule definition with non-boolean enabled raises ValueError."""
        rule_dict = {
            "rule_id": "TEST-003",
            "version": "1.0.0",
            "name": "Bad Enabled",
            "description": "desc",
            "severity": "Low",
            "enabled": "true",  # Not a boolean
            "config": {},
            "limitations": "none",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_rule_definition(rule_dict)
        self.assertIn("boolean", str(ctx.exception))

    def test_invalid_config_type(self) -> None:
        """Rule definition with non-dict config raises ValueError."""
        rule_dict = {
            "rule_id": "TEST-004",
            "version": "1.0.0",
            "name": "Bad Config",
            "description": "desc",
            "severity": "Low",
            "enabled": True,
            "config": ["not", "a", "dict"],
            "limitations": "none",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_rule_definition(rule_dict)
        self.assertIn("must be a dictionary", str(ctx.exception))

    def test_deterministic_config_hashing(self) -> None:
        """Config hash is deterministic and changes when config values change."""
        cfg1 = {"threshold": 5, "window_minutes": 10}
        cfg2 = {"window_minutes": 10, "threshold": 5}  # same content, different order
        cfg3 = {"threshold": 10, "window_minutes": 10}  # different value

        hash1 = compute_config_hash(cfg1)
        hash2 = compute_config_hash(cfg2)
        hash3 = compute_config_hash(cfg3)

        self.assertEqual(hash1, hash2, "Key order must not affect SHA-256 config hash")
        self.assertNotEqual(hash1, hash3, "Different config values must produce distinct hashes")
        self.assertEqual(len(hash1), 64, "SHA-256 hash must be 64 hexadecimal characters")


if __name__ == "__main__":
    unittest.main()
