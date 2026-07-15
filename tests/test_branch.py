import unittest

from riggit.branch import TicketExtractionError, extract_ticket


class TestExtractTicket(unittest.TestCase):
    def test_extracts_default_pattern(self):
        self.assertEqual(extract_ticket("feature/DT-123-login-fix"), "DT-123")

    def test_case_insensitive(self):
        self.assertEqual(extract_ticket("feature/dt-123-login-fix"), "dt-123")

    def test_no_match_returns_none(self):
        self.assertIsNone(extract_ticket("chore/cleanup-stuff"))

    def test_custom_pattern(self):
        self.assertEqual(extract_ticket("random/TICKET_9999", pattern=r"[A-Z]+_[0-9]+"), "TICKET_9999")

    def test_custom_pattern_named_group(self):
        ticket = extract_ticket("release/2024-DT-77", pattern=r"(?P<ticket>DT-\d+)")
        self.assertEqual(ticket, "DT-77")

    def test_invalid_pattern_raises(self):
        with self.assertRaises(TicketExtractionError):
            extract_ticket("feature/DT-123", pattern="[unclosed")


if __name__ == "__main__":
    unittest.main()
