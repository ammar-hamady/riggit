import unittest

from riggit.conventional_commits import validate_commit_message
from riggit.stats import compute_stats


def _result(message):
    return validate_commit_message(message)


class TestComputeStats(unittest.TestCase):
    def test_percent_compliant(self):
        records = [
            ("Alice", _result("feat: add thing")),
            ("Alice", _result("bad message")),
            ("Bob", _result("fix(api): correct bug")),
        ]
        stats = compute_stats(records)
        self.assertEqual(stats.total, 3)
        self.assertEqual(stats.compliant, 2)
        self.assertAlmostEqual(stats.percent_compliant, 66.7)

    def test_empty_records(self):
        stats = compute_stats([])
        self.assertEqual(stats.total, 0)
        self.assertEqual(stats.percent_compliant, 100.0)

    def test_violation_categories(self):
        records = [
            ("Alice", _result("bad message")),
            ("Alice", _result("weird message too")),
        ]
        stats = compute_stats(records)
        self.assertEqual(stats.violation_counts["malformed header"], 2)

    def test_by_author_breakdown(self):
        records = [
            ("Alice", _result("feat: ok")),
            ("Alice", _result("bad")),
            ("Bob", _result("fix: ok")),
        ]
        stats = compute_stats(records)
        self.assertEqual(stats.by_author["Alice"].total, 2)
        self.assertEqual(stats.by_author["Alice"].compliant, 1)
        self.assertEqual(stats.by_author["Bob"].total, 1)
        self.assertEqual(stats.by_author["Bob"].compliant, 1)


if __name__ == "__main__":
    unittest.main()
