import tempfile
import unittest
from pathlib import Path

from riggit.config import ConfigError, RiggitConfig, find_config_file, load_config


class TestConfig(unittest.TestCase):
    def test_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(tmp)
        self.assertIsNone(config.source)
        self.assertEqual(config.scope_required, False)
        self.assertEqual(config.max_header_length, 100)
        self.assertIn("feat", config.types)

    def test_loads_custom_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text(
                "types:\n  - feat\n  - task\n"
                "scope_required: true\n"
                "max_header_length: 50\n"
                "description_case: any\n"
                "no_trailing_period: false\n"
            )
            config = load_config(tmp)
        self.assertEqual(config.types, ("feat", "task"))
        self.assertTrue(config.scope_required)
        self.assertEqual(config.max_header_length, 50)
        self.assertEqual(config.description_case, "any")
        self.assertFalse(config.no_trailing_period)
        self.assertEqual(config.source, str(path))

    def test_partial_override_keeps_other_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("scope_required: true\n")
            config = load_config(tmp)
        self.assertTrue(config.scope_required)
        self.assertEqual(config.max_header_length, 100)
        self.assertIn("feat", config.types)

    def test_finds_config_in_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".riggitrc").write_text("scope_required: true\n")
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            found = find_config_file(nested)
        self.assertEqual(found, root / ".riggitrc")

    def test_invalid_yaml_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("types: [feat, fix\n")  # malformed YAML
            with self.assertRaises(ConfigError):
                load_config(tmp)

    def test_invalid_description_case_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("description_case: upper\n")
            with self.assertRaises(ConfigError):
                load_config(tmp)

    def test_empty_types_list_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".riggitrc"
            path.write_text("types: []\n")
            with self.assertRaises(ConfigError):
                load_config(tmp)


if __name__ == "__main__":
    unittest.main()
