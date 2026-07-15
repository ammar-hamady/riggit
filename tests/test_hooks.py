import subprocess
import tempfile
import unittest
from pathlib import Path

from riggit.hooks import HookError, install_hook, uninstall_hook


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "a@a.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "a"], check=True)


class TestHooks(unittest.TestCase):
    def test_install_creates_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            hook_path = install_hook(repo)
            self.assertTrue(hook_path.exists())
            self.assertIn("managed-by: riggit", hook_path.read_text())
            self.assertTrue(hook_path.stat().st_mode & 0o111)

    def test_uninstall_removes_riggit_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            install_hook(repo)
            removed = uninstall_hook(repo)
            self.assertTrue(removed)
            self.assertFalse((repo / ".git" / "hooks" / "commit-msg").exists())

    def test_uninstall_missing_hook_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            removed = uninstall_hook(repo)
            self.assertFalse(removed)

    def test_install_refuses_foreign_hook_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            hook_path = repo / ".git" / "hooks" / "commit-msg"
            hook_path.write_text("#!/usr/bin/env bash\necho custom\n")
            with self.assertRaises(HookError):
                install_hook(repo)
            install_hook(repo, force=True)
            self.assertIn("managed-by: riggit", hook_path.read_text())

    def test_uninstall_refuses_foreign_hook_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_repo(repo)
            hook_path = repo / ".git" / "hooks" / "commit-msg"
            hook_path.write_text("#!/usr/bin/env bash\necho custom\n")
            with self.assertRaises(HookError):
                uninstall_hook(repo)
            removed = uninstall_hook(repo, force=True)
            self.assertTrue(removed)


if __name__ == "__main__":
    unittest.main()
