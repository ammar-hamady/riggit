import tempfile
import unittest
from pathlib import Path

from riggit.config import (
    ConfigError,
    effective_values_for_file,
    get_raw_config_value,
    parse_config_value,
    set_config_value,
)


class TestParseConfigValue(unittest.TestCase):
    def test_types_split_on_comma(self):
        self.assertEqual(parse_config_value("types", "feat, fix,docs"), ["feat", "fix", "docs"])

    def test_bool_variants(self):
        for truthy in ("true", "True", "yes", "1", "on"):
            self.assertIs(parse_config_value("scope_required", truthy), True)
        for falsy in ("false", "False", "no", "0", "off"):
            self.assertIs(parse_config_value("scope_required", falsy), False)

    def test_invalid_bool_raises(self):
        with self.assertRaises(ConfigError):
            parse_config_value("scope_required", "maybe")

    def test_max_header_length_null(self):
        self.assertIsNone(parse_config_value("max_header_length", "null"))

    def test_max_header_length_int(self):
        self.assertEqual(parse_config_value("max_header_length", "72"), 72)

    def test_max_header_length_invalid_raises(self):
        with self.assertRaises(ConfigError):
            parse_config_value("max_header_length", "seventy")

    def test_description_case_validated(self):
        with self.assertRaises(ConfigError):
            parse_config_value("description_case", "upper")

    def test_unknown_key_raises(self):
        with self.assertRaises(ConfigError):
            parse_config_value("nonexistent", "x")


class TestSetConfigValue(unittest.TestCase):
    def test_creates_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            set_config_value(path, "scope_required", "true")
            self.assertTrue(path.is_file())
            self.assertTrue(get_raw_config_value(path, "scope_required"))

    def test_replaces_flow_style_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            set_config_value(path, "types", "feat,fix")
            set_config_value(path, "types", "feat,fix,chore")
            self.assertEqual(get_raw_config_value(path, "types"), ["feat", "fix", "chore"])
            # exactly one 'types:' line should remain
            lines = [l for l in path.read_text().splitlines() if l.startswith("types:")]
            self.assertEqual(len(lines), 1)

    def test_replaces_block_style_list_from_init_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text(
                "# a comment\n"
                "types:\n"
                "  - feat\n"
                "  - fix\n"
                "\n"
                "scope_required: false\n"
            )
            set_config_value(path, "types", "feat,task")
            content = path.read_text()
            self.assertIn("# a comment", content)
            self.assertIn("scope_required: false", content)
            self.assertEqual(get_raw_config_value(path, "types"), ["feat", "task"])
            self.assertNotIn("  - fix", content)

    def test_preserves_unrelated_keys_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("# keep me\nscope_required: false\nmax_header_length: 100\n")
            set_config_value(path, "scope_required", "true")
            content = path.read_text()
            self.assertIn("# keep me", content)
            self.assertIn("max_header_length: 100", content)
            self.assertIn("scope_required: true", content)

    def test_invalid_value_raises_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            with self.assertRaises(ConfigError):
                set_config_value(path, "description_case", "upper")
            self.assertFalse(path.exists())


class TestEffectiveValuesForFile(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = effective_values_for_file(Path(tmp) / ".riggitrc")
        self.assertEqual(values["scope_required"], False)

    def test_existing_file_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("scope_required: true\n")
            values = effective_values_for_file(path)
        self.assertEqual(values["scope_required"], True)


if __name__ == "__main__":
    unittest.main()
