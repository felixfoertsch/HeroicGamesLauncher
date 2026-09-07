"""Regression coverage for CalVer release documentation and conservative cleanup."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest
from datetime import datetime, timezone

from calver import REPOSITORY, next_version, version_fields
from release_cleanup import cleanup, legacy_releases, verify_replacement
from release_notes import DISCLOSURE, channel_notes, render_notes


def fixture():
    plan = {**version_fields("v2.22.1", "2026.09.06", 1), "repository": REPOSITORY,
            "upstream": {"tag": "v2.22.1"}, "candidate": "a" * 40, "base": "b" * 40,
            "patches": [{"original": "c" * 40, "commit": "d" * 40,
                         "status": "retained", "subject": "fix: Recover Nile login"}]}
    tag = plan["tag"]
    image = f"Heroic-{tag}-custom-x86_64.AppImage"
    names = ["build-info.json", "SHA256SUMS", "latest-linux.yml", image,
             f"Heroic-{tag}-source.tar.gz", f"Heroic-{tag}-custom-x64.tar.xz"]
    release = {"id": 3, "tag_name": tag, "draft": False, "prerelease": False,
               "published_at": "2026-09-06T17:00:00Z",
               "assets": [{"name": name, "state": "uploaded", "size": 100} for name in names]}
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{image}"
    feed = {"version": plan["version"], "releaseName": tag, "path": url, "files": [{"url": url}]}
    return plan, release, feed


class ReleaseDocumentationTests(unittest.TestCase):
    def test_disclosure_is_first_text(self):
        text = render_notes(fixture()[0])
        self.assertTrue(text.startswith(DISCLOSURE + "\n\n"))
        self.assertIn("Astra", text.splitlines()[0])

    def test_public_tag_is_padded_calver(self):
        text = render_notes(fixture()[0])
        self.assertIn("## Heroic v2.22.1-2026.09.06.1", text)
        self.assertIn("2.22.1-2026.9.6.1", text)
        self.assertIn("2.22.1_2026.09.06.1-1", text)

    def test_no_claim_of_live_mfa_testing(self):
        self.assertIn("do not substitute", render_notes(fixture()[0]))

    def test_signing_status_is_explicit(self):
        self.assertIn("not configured", render_notes(fixture()[0]))
        self.assertIn("signed `heroic-felix`", render_notes(fixture()[0], signed=True))

    def test_all_channel_descriptions_start_with_disclosure(self):
        for channel in ("pacman", "downstream-feed"):
            self.assertTrue(channel_notes(channel).startswith(DISCLOSURE))
            self.assertIn("not an application version", channel_notes(channel))

    def test_unknown_channel_rejected(self):
        with self.assertRaises(ValueError):
            channel_notes("latest")

    def test_other_repository_rejected(self):
        plan = fixture()[0]
        plan["repository"] = "Heroic-Games-Launcher/HeroicGamesLauncher"
        with self.assertRaises(ValueError):
            render_notes(plan)

    def test_invalid_commit_rejected(self):
        plan = fixture()[0]
        plan["candidate"] = "$(not-a-sha)"
        with self.assertRaises(ValueError):
            render_notes(plan)

    def test_multiline_patch_subject_rejected(self):
        plan = fixture()[0]
        plan["patches"][0]["subject"] += "\nInjected section"
        with self.assertRaises(ValueError):
            render_notes(plan)

    def test_counter_orders_numerically(self):
        versions = next_version("v2.22.1", ["v2.22.1-2026.09.06.9", "v2.22.1-2026.09.06.10"],
                                datetime(2026, 9, 6, 12, tzinfo=timezone.utc))
        self.assertEqual(versions["tag"], "v2.22.1-2026.09.06.11")

    def test_complete_replacement_and_feed_pass(self):
        plan, release, feed = fixture()
        verify_replacement(release, plan, feed)

    def test_incomplete_replacement_rejected(self):
        plan, release, feed = fixture()
        release["assets"] = release["assets"][:-1]
        with self.assertRaises(ValueError):
            verify_replacement(release, plan, feed)

    def test_stale_feed_rejected(self):
        plan, release, feed = fixture()
        feed["releaseName"] = "v2.22.1-felix.1.1"
        with self.assertRaises(ValueError):
            verify_replacement(release, plan, feed)

    def test_foreign_feed_url_rejected(self):
        plan, release, feed = fixture()
        feed["path"] = "https://example.invalid/file.AppImage"
        with self.assertRaises(ValueError):
            verify_replacement(release, plan, feed)

    def test_draft_replacement_rejected(self):
        plan, release, feed = fixture()
        release["draft"] = True
        with self.assertRaises(ValueError):
            verify_replacement(release, plan, feed)

    def test_cleanup_only_selects_older_published_run_id_versions(self):
        _, current, _ = fixture()
        old = {"tag_name": "v2.22.1-felix.34046063275.1", "draft": False,
               "published_at": "2026-09-06T16:46:47Z"}
        other = [dict(old, tag_name="pacman"), dict(old, tag_name="downstream-feed"),
                 dict(old, tag_name="v2.22.1-2026.09.05.1"), dict(old, tag_name="v2.22.1"),
                 dict(old, tag_name="v2.23.0-felix.10.1"), dict(old, draft=True),
                 dict(old, published_at="2026-09-07T00:00:00Z")]
        original = copy.deepcopy([old, *other, current])
        self.assertEqual(legacy_releases(original, current), [old])
        self.assertEqual(original, [old, *other, current])


class CleanupExecutionTests(unittest.TestCase):
    def run_cleanup(self, apply=True, wrong_checksum=False, changed_latest=False, legacy_latest=False):
        plan, current, feed = fixture()
        old = {"id": 1, "tag_name": "v2.22.1-felix.34046063275.1", "draft": False,
               "published_at": "2026-09-06T16:46:47Z"}
        channel = {"id": 2, "tag_name": "downstream-feed", "draft": False}
        edits = []
        latest_reads = 0

        def fake_gh(*args):
            nonlocal latest_reads
            if args[0] == "api" and "--paginate" in args:
                return json.dumps([[old, channel, current]])
            if args[0] == "api" and args[-1].endswith("/latest"):
                latest_reads += 1
                if legacy_latest:
                    return json.dumps(old)
                return json.dumps(dict(current, id=999) if changed_latest and latest_reads > 1 else current)
            if args[:2] == ("release", "download"):
                root = Path(args[args.index("--dir") + 1])
                if args[2] == "downstream-feed":
                    (root / "latest-linux.yml").write_text(json.dumps(feed))
                else:
                    payload = json.dumps(plan).encode()
                    (root / "build-info.json").write_bytes(payload)
                    digest = "0" * 64 if wrong_checksum else hashlib.sha256(payload).hexdigest()
                    (root / "SHA256SUMS").write_text(digest + "  build-info.json\n")
                return ""
            if args[:2] == ("release", "edit"):
                body = Path(args[args.index("--notes-file") + 1]).read_text()
                edits.append((args, body))
                return ""
            raise AssertionError(f"Unexpected GitHub operation: {args}")

        with patch.dict("os.environ", {"GITHUB_REPOSITORY": REPOSITORY}), patch("release_cleanup.gh", side_effect=fake_gh):
            cleanup(apply)
        return edits

    def test_apply_edits_descriptions_and_archives_without_deleting(self):
        edits = self.run_cleanup()
        self.assertEqual(len(edits), 3)
        for args, body in edits:
            self.assertTrue(body.startswith(DISCLOSURE))
            self.assertNotIn("--tag", args)
            self.assertNotIn("--target", args)
            self.assertEqual(args[:2], ("release", "edit"))
        self.assertIn("--draft=true", edits[-1][0])
        self.assertIn("--latest=false", edits[-1][0])

    def test_dry_run_does_not_mutate(self):
        self.assertEqual(self.run_cleanup(apply=False), [])

    def test_legacy_latest_preserves_old_releases(self):
        self.assertEqual(self.run_cleanup(legacy_latest=True), [])

    def test_checksum_failure_prevents_edits(self):
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.run_cleanup(wrong_checksum=True)

    def test_changed_latest_prevents_edits(self):
        with self.assertRaisesRegex(ValueError, "changed during"):
            self.run_cleanup(changed_latest=True)


if __name__ == "__main__":
    unittest.main()
