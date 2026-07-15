import unittest

from riggit.config import RiggitConfig
from riggit.scan import apply_simple_fixes


class TestApplySimpleFixes(unittest.TestCase):
    def setUp(self):
        self.config = RiggitConfig.defaults()

    def test_lowercases_description(self):
        fixed, changes = apply_simple_fixes("feat: Add Something New", self.config)
        self.assertEqual(fixed, "feat: add Something New")
        self.assertIn("lowercased description", changes)

    def test_removes_trailing_period(self):
        fixed, changes = apply_simple_fixes("fix: correct crash.", self.config)
        self.assertEqual(fixed, "fix: correct crash")
        self.assertIn("removed trailing period", changes)

    def test_both_fixes_applied(self):
        fixed, changes = apply_simple_fixes("feat(api): Add Something New.", self.config)
        self.assertEqual(fixed, "feat(api): add Something New")
        self.assertEqual(len(changes), 2)

    def test_no_changes_for_compliant_message(self):
        fixed, changes = apply_simple_fixes("feat: add thing", self.config)
        self.assertEqual(fixed, "feat: add thing")
        self.assertEqual(changes, [])

    def test_malformed_header_left_untouched(self):
        fixed, changes = apply_simple_fixes("Not a conventional commit.", self.config)
        self.assertEqual(fixed, "Not a conventional commit.")
        self.assertEqual(changes, [])

    def test_preserves_body_lines(self):
        message = "feat: Add thing.\n\nSome body text.\n"
        fixed, changes = apply_simple_fixes(message, self.config)
        self.assertTrue(changes)
        self.assertIn("Some body text.", fixed)

    def test_empty_message_untouched(self):
        fixed, changes = apply_simple_fixes("", self.config)
        self.assertEqual(fixed, "")
        self.assertEqual(changes, [])

    def test_respects_config_disabling_checks(self):
        config = RiggitConfig(
            types=self.config.types,
            scope_required=False,
            max_header_length=None,
            description_case="any",
            no_trailing_period=False,
        )
        fixed, changes = apply_simple_fixes("feat: Add Something New.", config)
        self.assertEqual(fixed, "feat: Add Something New.")
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
