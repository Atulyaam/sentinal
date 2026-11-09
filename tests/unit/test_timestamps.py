"""Unit tests for timestamp parsing and UTC normalization."""

import unittest
from backend.normalization.timestamps import parse_and_normalize_timestamp


class TestTimestamps(unittest.TestCase):
    """Test suite for timestamp normalization."""

    def test_utc_iso_string_with_z(self) -> None:
        ts, is_naive = parse_and_normalize_timestamp("2026-11-09T08:00:15Z")
        self.assertEqual(ts, "2026-11-09T08:00:15Z")
        self.assertFalse(is_naive)

    def test_offset_conversion_to_utc(self) -> None:
        # +02:00 -> should subtract 2 hours to get UTC
        ts, is_naive = parse_and_normalize_timestamp("2026-11-09T10:00:15+02:00")
        self.assertEqual(ts, "2026-11-09T08:00:15Z")
        self.assertFalse(is_naive)

        # -05:00 -> should add 5 hours to get UTC
        ts2, is_naive2 = parse_and_normalize_timestamp("2026-11-09T03:00:15-05:00")
        self.assertEqual(ts2, "2026-11-09T08:00:15Z")
        self.assertFalse(is_naive2)

    def test_naive_timestamp_flagged(self) -> None:
        ts, is_naive = parse_and_normalize_timestamp("2026-11-09T08:00:15")
        self.assertEqual(ts, "2026-11-09T08:00:15Z")
        self.assertTrue(is_naive)

        ts2, is_naive2 = parse_and_normalize_timestamp("2026-11-09 08:00:15")
        self.assertEqual(ts2, "2026-11-09T08:00:15Z")
        self.assertTrue(is_naive2)

    def test_subsecond_precision_preserved(self) -> None:
        ts, is_naive = parse_and_normalize_timestamp("2026-11-09T08:00:15.123456Z")
        self.assertEqual(ts, "2026-11-09T08:00:15.123456Z")
        self.assertFalse(is_naive)

    def test_epoch_numeric_and_string(self) -> None:
        # 1762675200 is 2025-11-09 08:00:00 UTC (or similar)
        ts, is_naive = parse_and_normalize_timestamp(1762675200)
        self.assertTrue(ts.endswith("Z"))
        self.assertFalse(is_naive)

        ts_str, is_naive_str = parse_and_normalize_timestamp("1762675200")
        self.assertEqual(ts, ts_str)
        self.assertFalse(is_naive_str)

    def test_invalid_timestamps_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp(None)

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("")

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("not-a-timestamp")

        with self.assertRaises(ValueError):
            parse_and_normalize_timestamp("2026-99-99T99:99:99")


if __name__ == "__main__":
    unittest.main()

