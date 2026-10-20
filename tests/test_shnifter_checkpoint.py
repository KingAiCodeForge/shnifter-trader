"""Detached rollback anchors and explicit v1 preservation; no brokerage/network."""
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shnifter_order_events import PaperEventStore, IntegrityError


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="paper checkpoint spaces ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "paper v2.sqlite"
        self.store = PaperEventStore.create(self.path)

    def rollback_halt(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DROP TRIGGER events_no_delete")
            db.execute("DELETE FROM events WHERE seq=2")

    def test_anchor_detects_valid_prefix_that_loses_halt_without_writing(self):
        self.store.append("stop", "HALT", {"reason": "manual hold"})
        anchor = self.store.export_checkpoint()
        self.rollback_halt()
        original = self.path.read_bytes()
        self.assertFalse(self.store.status()["manual_halt"])
        anchored = PaperEventStore(self.path, checkpoint=anchor)
        with self.assertRaisesRegex(IntegrityError, "rollback"):
            anchored.status()
        with self.assertRaisesRegex(IntegrityError, "rollback"):
            anchored.append("new-stop", "HALT", {"reason": "hold"})
        self.assertEqual(original, self.path.read_bytes())

    def test_mismatched_chain_is_rejected(self):
        anchor = self.store.export_checkpoint()
        anchor["head_hash"] = "0" * 64
        with self.assertRaisesRegex(IntegrityError, "trusted checkpoint"):
            PaperEventStore(self.path, checkpoint=anchor).verify()

    def test_extension_is_verified_but_does_not_claim_latest_freshness(self):
        anchor = self.store.export_checkpoint()
        self.store.append("stop", "HALT", {"reason": "manual hold"})
        result = PaperEventStore(self.path, checkpoint=anchor).status()
        self.assertTrue(result["checkpoint_verified"])
        self.assertEqual(result["events_after_checkpoint"], 1)
        self.assertFalse(result["freshness_proven"])

    def test_stale_anchor_cannot_detect_lost_events_after_anchor(self):
        anchor = self.store.export_checkpoint()
        self.store.append("stop", "HALT", {"reason": "manual hold"})
        self.rollback_halt()
        result = PaperEventStore(self.path, checkpoint=anchor).status()
        self.assertTrue(result["checkpoint_verified"])
        self.assertFalse(result["manual_halt"])
        self.assertFalse(result["freshness_proven"])

    def test_unanchored_status_explicitly_lacks_freshness(self):
        result = self.store.verify()
        self.assertFalse(result["checkpoint_verified"])
        self.assertFalse(result["freshness_proven"])
        self.assertIsNone(result["checkpoint_event_count"])

    def test_anchor_input_is_validated_and_copied(self):
        anchor = self.store.export_checkpoint()
        anchored = PaperEventStore(self.path, checkpoint=anchor)
        anchor["head_hash"] = "0" * 64
        self.assertTrue(anchored.verify()["checkpoint_verified"])
        valid = self.store.export_checkpoint()
        for mutation in ({"event_count": True}, {"event_count": 0},
                         {"head_hash": "xyz"}, {"engine": "shnifter.paper-events.v1"},
                         {"extra": 1}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                PaperEventStore(self.path, checkpoint={**valid, **mutation})

    def test_v1_preserved_and_v2_created_at_separate_new_path(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE metadata SET version='shnifter.paper-events.v1'")
        original = self.path.read_bytes()
        with self.assertRaisesRegex(IntegrityError, "separate NEW --db path"):
            self.store.status()
        with self.assertRaises(FileExistsError):
            PaperEventStore.create(self.path)
        separate = self.root / "new paper v2.sqlite"
        new_store = PaperEventStore.create(separate)
        self.assertEqual(new_store.status()["event_count"], 1)
        self.assertEqual(original, self.path.read_bytes())

    def cli(self, *args):
        script = Path(__file__).resolve().parents[1] / "shnifter_cli.py"
        return subprocess.run([sys.executable, str(script), "paper-events", *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=20)

    def test_cli_export_validate_no_overwrite_and_database_preservation(self):
        anchor = self.root / "detached anchor.json"
        result = self.cli("checkpoint", "--db", self.path, "--output", anchor)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["freshness_proven"])
        original = anchor.read_bytes()
        repeated = self.cli("checkpoint", "--db", self.path, "--output", anchor)
        self.assertEqual(repeated.returncode, 1)
        self.assertEqual(original, anchor.read_bytes())
        self.assertEqual(self.cli("verify", "--db", self.path, "--checkpoint", anchor).returncode, 0)
        before = self.path.read_bytes()
        collision = self.cli("checkpoint", "--db", self.path, "--output", self.path)
        self.assertEqual(collision.returncode, 1)
        self.assertEqual(before, self.path.read_bytes())

    def test_cli_invalid_checkpoint_has_structured_failure_and_no_write(self):
        anchor = self.root / "bad.json"
        anchor.write_text("null", encoding="utf-8")
        original = self.path.read_bytes()
        result = self.cli("halt", "--db", self.path, "--event-id", "stop", "--reason", "hold",
                          "--checkpoint", anchor)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stderr)["live_authorized"])
        self.assertEqual(original, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
