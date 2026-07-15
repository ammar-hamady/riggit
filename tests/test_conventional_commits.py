import unittest

from riggit.conventional_commits import validate_commit_message


class TestValidateCommitMessage(unittest.TestCase):
    def test_valid_simple(self):
        result = validate_commit_message("fix: correct minor typos in code")
        self.assertTrue(result.valid)
        self.assertEqual(result.commit_type, "fix")
        self.assertIsNone(result.scope)
        self.assertFalse(result.breaking)

    def test_valid_with_scope(self):
        result = validate_commit_message("feat(parser): add ability to parse arrays")
        self.assertTrue(result.valid)
        self.assertEqual(result.commit_type, "feat")
        self.assertEqual(result.scope, "parser")

    def test_breaking_bang(self):
        result = validate_commit_message("feat!: send an email when a product is shipped")
        self.assertTrue(result.valid)
        self.assertTrue(result.breaking)

    def test_breaking_footer(self):
        message = (
            "feat: allow config object to extend other configs\n\n"
            "BREAKING CHANGE: `extends` key in config file is now used for extending other config files\n"
        )
        result = validate_commit_message(message)
        self.assertTrue(result.valid)
        self.assertTrue(result.breaking)

    def test_invalid_no_type(self):
        result = validate_commit_message("updated stuff")
        self.assertFalse(result.valid)
        self.assertTrue(result.errors)

    def test_invalid_unknown_type(self):
        result = validate_commit_message("feature: add new thing")
        self.assertFalse(result.valid)

    def test_invalid_empty_scope(self):
        result = validate_commit_message("feat(): add new thing")
        self.assertFalse(result.valid)

    def test_invalid_missing_space_after_colon(self):
        result = validate_commit_message("feat:add new thing")
        self.assertFalse(result.valid)

    def test_invalid_empty_message(self):
        result = validate_commit_message("")
        self.assertFalse(result.valid)

    def test_uppercase_type_rejected(self):
        result = validate_commit_message("Feat: add new thing")
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()
