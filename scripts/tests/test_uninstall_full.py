"""Purge guard tests. No host services, packages, databases or VM files are changed."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "full_purge", Path(__file__).parents[1] / "uninstall_full.py"
)
purge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(purge)


class PurgeGuardsTests(unittest.TestCase):
    def test_source_nested_mount_and_git_checkout_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "app"
            target.mkdir()
            for project, mounts in (
                (target / "source", []),
                (root / "source", [target / "data"]),
            ):
                with self.assertRaises(ValueError):
                    purge.check_tree(target, project, mounts)
            (target / ".git").mkdir()
            with self.assertRaises(ValueError):
                purge.check_tree(target, root / "source", [])

    def test_redirected_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "original").mkdir()
            (root / "redirect").symlink_to(root / "original", target_is_directory=True)
            with self.assertRaises(ValueError):
                purge.check_tree(root / "redirect", root / "source", [])

    def test_preview_and_missing_confirmation_never_mutate_host(self):
        for arguments in ([], ["--dry-run"], ["--apply", "--dry-run"], ["--apply"]):
            with (
                self.subTest(arguments=arguments),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                project, config, state, app = [
                    root / name for name in ("source", "config", "state", "app")
                ]
                for path in (project, config, state, app):
                    path.mkdir(mode=0o700)
                marker = config / "install-secrets.env"
                marker.write_text("deployment marker")
                marker.chmod(0o600)
                for name in ("agent.env", "management.env"):
                    path = config / name
                    path.write_text("")
                    path.chmod(0o600)
                record = state / "added-packages.txt"
                record.write_text("")
                record.chmod(0o600)
                settings = {
                    "management.env": {
                        "DATABASE_URL": "postgresql://cloudvirt:test@127.0.0.1/cloudvirt"
                    },
                    "agent.env": {
                        "CLOUDVIRT_DISK_DIR": str(root / "disks"),
                        "CLOUDVIRT_IMAGE_DIR": str(root / "images"),
                    },
                }
                real_open = open
                with (
                    patch.object(purge, "CONFIG", config),
                    patch.object(purge, "STATE", state),
                    patch.object(purge, "APP", app),
                    patch.object(purge, "TREES", [app, config]),
                    patch.object(
                        purge,
                        "env_file",
                        side_effect=lambda name, settings=settings: settings[name],
                    ),
                    patch.object(
                        purge,
                        "inventory",
                        return_value={
                            "domains": [],
                            "pools": [],
                            "files": [],
                            "preserved_originals": [],
                        },
                    ),
                    patch.object(purge, "run", return_value="") as run,
                    patch.object(purge.pwd, "getpwnam", side_effect=KeyError),
                    patch.object(purge.os, "geteuid", return_value=0),
                    patch.object(purge, "trusted"),
                    patch.object(
                        purge,
                        "open",
                        side_effect=lambda *a, real_open=real_open, root=root, **k: (
                            real_open(root / "lock", "a")
                        ),
                        create=True,
                    ),
                    patch.object(purge, "remove_nginx") as nginx,
                    patch.object(purge.shutil, "rmtree") as remove,
                    patch(
                        "sys.argv",
                        ["uninstall-full", "--project-dir", str(project), *arguments],
                    ),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    if arguments == ["--apply"]:
                        with self.assertRaises(SystemExit):
                            purge.main()
                    else:
                        purge.main()
                    nginx.assert_not_called()
                    remove.assert_not_called()
                    self.assertEqual(run.call_args_list[0].args[:2], ("findmnt", "-rn"))
                    self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
