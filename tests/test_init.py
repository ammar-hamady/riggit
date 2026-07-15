import tempfile
import unittest
from pathlib import Path

from riggit.init import InitError, init_config_file


class TestInit(unittest.TestCase):
    def test_creates_riggitrc(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = init_config_file(tmp)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, ".riggitrc")
            self.assertIn("scope_required: false", path.read_text())

    def test_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            init_config_file(tmp)
            with self.assertRaises(InitError):
                init_config_file(tmp)

    def test_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = init_config_file(tmp)
            path.write_text("scope_required: true\n")
            init_config_file(tmp, force=True)
            self.assertIn("scope_required: false", path.read_text())

    def test_nonexistent_directory_raises(self):
        with self.assertRaises(InitError):
            init_config_file("/nonexistent/path/xyz")


if __name__ == "__main__":
    unittest.main()
