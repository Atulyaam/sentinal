"""Unit tests for timestamp parsing and UTC normalization."""

import unittest
from backend.normalization.timestamps import (
    NaiveTimestampError,
    format_utc_iso,
    parse_and_normalize_timestamp,
)


class TestTimestamps(unittest.TestCase):
    """Test suite for timestamp normalization and timezone enforcement."""

    def test_utc_iso_string_with_z(self) -> None:
        ts, raw = parse_and_normalize_timestamp("2026-11-09T08:00:15Z")
        self.assertEqual(ts, "2026-11-09T08:00:15Z")
        self.assertEqual(raw, "2026-11-09T08:00:15Z")

    def test_offset_conversion_to_utc(self) -> None:
        # +02:00 -> should subtract 2 hours to get UTC
        ts, raw = parse_and_normalize_timestamp("2026-11-09T10:00:15+02:00")
        self.assertEqual(ts, "2026-11-09T08:00:15Z")
        self.assertEqual(raw, "2026-11-09T10:00:15+02:00")

        # -05:00 -> should add 5 hours to get UTC
        ts2, raw2 = parse_and_normalize_timestamp("2026-11-09T03:00:15-05:00")
        self.assertEqual(ts2, "2026-11-09T08:00:15Z")
        self.assertEqual(raw2, "2026-11-09T03:00:15-05:00")

    def test_day_boundary_crossing_with_offset(self) -> None:
        # 01:30 AM in +02:00 crosses into previous day 23:30 in UTC
        ts, raw = parse_and_normalize_timestamp("2026-11-09T01:30:00+02:00")
        self.assertEqual(ts, "2026-11-08T23:30:00Z")
        self.assertEqual(raw, "2026-11-09T01:30:00+02:00")

    def test_naive_timestamps_rejected_without_utc_assumption(self) -> None:
        # ISO format without offset
        with self.assertRaises(NaiveTimestampError) as ctx1:
            parse_and_normalize_timestamp("2026-11-09T08:00:15")
        self.assertIn("cannot assume UTC", str(ctx1.exception))

        # Space-separated format without offset
        with self.assertRaises(NaiveTimestampError) as ctx2:
            parse_and_normalize_timestamp("2026-11-09 08:00:15")
        self.assertIn("cannot assume UTC", str(ctx2.exception))

        # Slash-separated format without offset
        with self.assertRaises(NaiveTimestampError) as ctx3:
            parse_and_normalize_timestamp("2026/11/09 08:00:15")
        self.assertIn("cannot assume UTC", str(ctx3.exception))

    def test_subsecond_precision_preserved(self) -> None:
        ts, raw = parse_and_normalize_timestamp("2026-11-09T08:00:15.123456Z")
        self.assertEqual(ts, "2026-11-09T08:00:15.123456Z")
        self.assertEqual(raw, "2026-11-09T08:00:15.123456Z")

    def test_epoch_numeric_and_string(self) -> None:
        # Numeric epoch
        ts, raw = parse_and_normalize_timestamp(1762675200)
        self.assertTrue(ts.endswith("Z"))
        self.assertEqual(raw, "1762675200")

        # String epoch
        ts_str, raw_str = parse_and_normalize_timestamp("1762675200")
        self.assertEqual(ts, ts_str)
        self.assertEqual(raw_str, "1762675200")

        # Millisecond epoch
        ts_ms, _ = parse_and_normalize_timestamp(1762675200000)
        self.assertEqual(ts, ts_ms)

    def test_invalid_timestamps_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp(None)

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("")

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("   ")

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("not-a-timestamp")

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("2026-99-99T99:99:99")


if __name__ == "__main__":
    unittest.main()
