from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from wtfssd import cleaners
from wtfssd.config import DEFAULTS


def no_apps_running(argv, timeout=15):
    return None  # pgrep finds nothing → run_cmd semantics: None


def app_running(argv, timeout=15):
    if argv[0] == "pgrep":
        return "1234 Cursor\n"
    return None


class _HomePath(type(Path())):
    """Path subclass allowing attribute assignment.

    Python 3.14 gives pathlib classes __slots__ and no __dict__, so the
    brief's plain-Path `home._td = td` keep-alive raises AttributeError.
    A subclass without __slots__ gets a __dict__ and keeps the same
    semantics (isinstance Path, home._td cleanup)."""


def make_home() -> Path:
    td = tempfile.TemporaryDirectory()
    home = _HomePath(td.name)
    home._td = td  # keep alive
    return home


def put(root: Path, rel: str, size: int = 100) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    return p


class TestDenylist(unittest.TestCase):
    def test_denies_protected(self):
        home = Path("/Users/test")
        self.assertTrue(cleaners.is_denied(home / "Documents" / "x", home))
        self.assertTrue(cleaners.is_denied(home / "Desktop" / "x", home))
        self.assertTrue(cleaners.is_denied(Path("/etc/hosts"), home))
        self.assertTrue(cleaners.is_denied(home, home))
        self.assertFalse(cleaners.is_denied(home / "Library" / "Caches" / "x", home))
        # APFS is case-insensitive; a lowercase "documents" is still Documents.
        self.assertTrue(cleaners.is_denied(home / "documents" / "x", home))
        self.assertTrue(cleaners.is_denied(home / "DOCUMENTS" / "x", home))
        self.assertTrue(cleaners.is_denied(home / "desktop" / "x", home))


class TestCleanTarget(unittest.TestCase):
    def test_dry_run_changes_nothing(self):
        home = make_home()
        f = put(home, "Library/Application Support/Cursor/Cache/junk.bin", 500)
        res = cleaners.clean_target("cursor-caches", home=home,
                                    config=DEFAULTS, runner=no_apps_running)
        self.assertFalse(res.applied)
        self.assertEqual(res.actions[0].action, "would-trash")
        self.assertEqual(res.actions[0].size_bytes, 500)
        self.assertTrue(f.exists())
        home._td.cleanup()

    def test_apply_moves_to_trash(self):
        home = make_home()
        f = put(home, "Library/Application Support/Cursor/Cache/junk.bin", 500)
        res = cleaners.clean_target("cursor-caches", home=home, config=DEFAULTS,
                                    apply=True, runner=no_apps_running)
        self.assertTrue(res.applied)
        self.assertFalse(f.exists())
        self.assertTrue((home / ".Trash" / "Cache").exists())
        self.assertEqual(res.freed_bytes, 500)
        self.assertEqual(res.actions[0].action, "trashed")
        home._td.cleanup()

    def test_guard_app_running_skips(self):
        home = make_home()
        f = put(home, "Library/Application Support/Cursor/Cache/junk.bin", 500)
        res = cleaners.clean_target("cursor-caches", home=home, config=DEFAULTS,
                                    apply=True, runner=app_running)
        self.assertIsNotNone(res.skipped_reason)
        self.assertTrue(f.exists())
        # --force overrides
        res2 = cleaners.clean_target("cursor-caches", home=home, config=DEFAULTS,
                                     apply=True, force=True, runner=app_running)
        self.assertTrue(res2.applied)
        self.assertFalse(f.exists())
        home._td.cleanup()

    def test_backup_first_copies_db(self):
        home = make_home()
        db = put(home, "Library/Application Support/Cursor/User/globalStorage/state.vscdb", 900)
        backup = home / "backups"
        res = cleaners.clean_target("cursor-vscdb", home=home, config=DEFAULTS,
                                    apply=True, backup_dir=backup,
                                    runner=no_apps_running)
        self.assertEqual(res.actions[0].action, "backed-up+trashed")
        self.assertFalse(db.exists())
        backups = list(backup.rglob("state.vscdb"))
        self.assertEqual(len(backups), 1)
        home._td.cleanup()

    def test_user_caches_top_n(self):
        home = make_home()
        caches = home / "Library" / "Caches"
        for i in range(12):
            d = caches / f"app{i}"
            d.mkdir(parents=True)
            (d / "blob").write_bytes(b"x" * ((i + 1) * 1024 * 1024 // 2))
        cfg = dict(DEFAULTS)
        cfg["clean"] = {"node_stale_days": 30, "caches_top_n": 3, "caches_min_mb": 1}
        res = cleaners.clean_target("user-caches", home=home, config=cfg,
                                    runner=no_apps_running)
        self.assertEqual(len(res.actions), 3)
        names = {Path(a.path).name for a in res.actions}
        self.assertEqual(names, {"app11", "app10", "app9"})
        home._td.cleanup()

    def test_node_modules_stale_only(self):
        home = make_home()
        proj = home / "proj"
        fresh = proj / "fresh" / "node_modules"
        stale = proj / "old" / "node_modules"
        fresh.mkdir(parents=True)
        stale.mkdir(parents=True)
        (stale / "pkg.js").write_bytes(b"x" * 100)
        old = time.time() - 40 * 86400
        os.utime(stale, (old, old))
        cfg = dict(DEFAULTS)
        cfg["projects"] = [str(proj)]
        res = cleaners.clean_target("node-modules-stale", home=home, config=cfg,
                                    runner=no_apps_running)
        self.assertEqual([Path(a.path).name for a in res.actions], ["node_modules"])
        self.assertIn("old", res.actions[0].path)
        home._td.cleanup()

    def test_unknown_target(self):
        with self.assertRaises(KeyError):
            cleaners.clean_target("nope", home=Path("/tmp"),
                                  config=DEFAULTS, runner=no_apps_running)

    def test_trash_empties_itself_on_apply(self):
        home = make_home()
        put(home, ".Trash/old-junk.bin", 300)
        res = cleaners.clean_target("trash", home=home, config=DEFAULTS,
                                    apply=True, runner=no_apps_running)
        self.assertEqual(res.freed_bytes, 300)
        self.assertFalse((home / ".Trash" / "old-junk.bin").exists())
        self.assertEqual(res.actions[0].action, "deleted")
        home._td.cleanup()

    def test_trash_dry_run_labels_would_delete(self):
        home = make_home()
        put(home, ".Trash/old-junk.bin", 300)
        res = cleaners.clean_target("trash", home=home, config=DEFAULTS,
                                    runner=no_apps_running)
        self.assertFalse(res.applied)
        self.assertEqual(res.actions[0].action, "would-delete")
        self.assertTrue((home / ".Trash" / "old-junk.bin").exists())
        home._td.cleanup()

    def test_hard_dry_run_labels_would_delete(self):
        home = make_home()
        put(home, "Library/Application Support/Cursor/Cache/junk.bin", 500)
        res = cleaners.clean_target("cursor-caches", home=home, config=DEFAULTS,
                                    hard=True, runner=no_apps_running)
        self.assertFalse(res.applied)
        self.assertEqual(res.actions[0].action, "would-delete")
        home._td.cleanup()

    def test_trash_unlinks_symlink_without_following(self):
        home = make_home()
        target = put(home, "keep-me.txt", 80)
        trash = home / ".Trash"
        trash.mkdir()
        link = trash / "alias-to-keep"
        link.symlink_to(target)
        res = cleaners.clean_target("trash", home=home, config=DEFAULTS,
                                    apply=True, runner=no_apps_running)
        self.assertEqual(res.actions[0].action, "deleted")
        self.assertFalse(link.exists())
        self.assertTrue(target.exists())
        self.assertEqual(target.read_bytes(), b"x" * 80)
        home._td.cleanup()

    def test_snapshots_stay_under_cursor_root(self):
        home = make_home()
        outside = home / "src" / "app" / ".git" / "objects" / "pack"
        outside.mkdir(parents=True)
        (outside / "evil.pack").write_bytes(b"x" * 50)
        cur = home / ".cursor"
        (cur / "idx").mkdir(parents=True)
        (cur / "idx" / "ok.pack").write_bytes(b"y" * 10)
        (cur / "link").symlink_to(home / "src")
        res = cleaners.clean_target("cursor-snapshots", home=home,
                                    config=DEFAULTS, runner=no_apps_running)
        paths = [a.path for a in res.actions]
        self.assertTrue(any(p.endswith("ok.pack") for p in paths))
        self.assertFalse(any("evil.pack" in p for p in paths))
        home._td.cleanup()

    def test_backup_refuses_symlink(self):
        # A symlink must not be followed into a backup copy (or deleted as
        # if it were the regular file). No payload, just a local temp link.
        home = make_home()
        secret = put(home, "secret.txt", 900)
        gs = home / "Library/Application Support/Cursor/User/globalStorage"
        gs.mkdir(parents=True)
        link = gs / "state.vscdb"
        link.symlink_to(secret)
        backup = home / "backups"
        res = cleaners.clean_target("cursor-vscdb", home=home, config=DEFAULTS,
                                    apply=True, backup_dir=backup,
                                    runner=no_apps_running)
        self.assertEqual(res.actions[0].action, "denied-symlink")
        self.assertTrue(secret.exists())
        self.assertTrue(link.is_symlink())
        self.assertEqual(secret.read_bytes(), b"x" * 900)
        if backup.exists():
            self.assertEqual(list(backup.rglob("secret.txt")), [])
            self.assertEqual(list(backup.rglob("state.vscdb")), [])
        home._td.cleanup()

    def test_trash_dest_unique_on_collision(self):
        home = make_home()
        first = put(home, "Library/Application Support/Cursor/Cache/a.bin", 10)
        # Seed a trash name that would collide with the Cache directory.
        (home / ".Trash").mkdir()
        (home / ".Trash" / "Cache").mkdir()
        res = cleaners.clean_target("cursor-caches", home=home, config=DEFAULTS,
                                    apply=True, runner=no_apps_running)
        self.assertTrue(res.applied)
        self.assertFalse(first.exists())
        trashed = list((home / ".Trash").iterdir())
        self.assertGreaterEqual(len(trashed), 2)
        home._td.cleanup()


if __name__ == "__main__":
    unittest.main()
