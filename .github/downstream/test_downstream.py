"""Real-Git regression tests. Network calls are redirected to temporary local repositories."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import downstream as d


class DownstreamTests(unittest.TestCase):
    def setUp(self):
        context = patch.dict(os.environ, {"GITHUB_OUTPUT": os.devnull, "GITHUB_STEP_SUMMARY": os.devnull})
        context.start()
        self.addCleanup(context.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "origin.git"
        d.command(["git", "init", "-b", "main", str(self.repo)])
        d.command(["git", "init", "--bare", str(self.remote)])
        self.base = self.commit({"package.json": json.dumps({"version": "2.0.0", "packageManager": "pnpm@10.28.0"}),
                                 "shared.txt": "original\n"}, "upstream baseline")
        self.a = self.commit({"a.txt": "feature A\n"}, "feature A")
        self.b = self.commit({"b.txt": "feature B\n"}, "feature B")
        d.git(self.repo, "remote", "add", "origin", str(self.remote))
        d.git(self.repo, "push", "origin", "main", f"{self.base}:refs/heads/downstream-base")
        self.source = self.root / "source"
        self.output = self.root / "output"
        self.real_git = d.git

    def commit(self, files, message):
        for name, contents in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        d.git(self.repo, "add", ".")
        d.git(self.repo, "commit", "-m", message)
        return d.git(self.repo, "rev-parse", "HEAD")

    def upstream(self, files=None, cherry=None):
        d.git(self.repo, "checkout", "--detach", self.base)
        new_base = self.commit(files or {"new-upstream.txt": "new release\n"}, "new upstream release")
        if cherry:
            d.git(self.repo, "cherry-pick", cherry)
            new_base = d.git(self.repo, "rev-parse", "HEAD")
        d.git(self.repo, "checkout", "main")
        return new_base

    def plan(self, upstream=None, event="push"):
        upstream = upstream or self.base
        d.git(self.repo, "tag", "-f", "v2.0.0", upstream)
        d.git(self.repo, "push", "--force", "origin", "refs/tags/v2.0.0")

        def local_network(repo, *args):
            args = tuple(str(self.remote) if a == f"https://github.com/{d.UPSTREAM}.git" else a for a in args)
            return self.real_git(repo, *args)

        with patch.object(d, "git", side_effect=local_network):
            return d.prepare(self.repo, self.source, self.output,
                             {"tag_name": "v2.0.0", "draft": False, "prerelease": False},
                             "12345.1", event)

    def test_replay_is_linear_and_preserves_original_branches(self):
        new_base = self.upstream()
        candidate, results = d.replay(self.repo, self.source, self.base, self.b, new_base)
        self.assertEqual(len(d.patch_series(self.repo, new_base, candidate)), 2)
        self.assertEqual([p["status"] for p in results], ["replayed", "replayed"])
        self.assertEqual((self.source / "a.txt").read_text(), "feature A\n")
        self.assertEqual((self.source / "b.txt").read_text(), "feature B\n")
        self.assertEqual(d.git(self.repo, "rev-parse", "main"), self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.b)

    def test_only_equivalent_upstream_patch_is_skipped(self):
        new_base = self.upstream(cherry=self.a)
        candidate, results = d.replay(self.repo, self.source, self.base, self.b, new_base)
        self.assertEqual([p["status"] for p in results], ["upstream-equivalent", "replayed"])
        self.assertTrue((self.source / "a.txt").exists())
        self.assertTrue((self.source / "b.txt").exists())
        self.assertEqual(len(d.patch_series(self.repo, new_base, candidate)), 1)

    def test_dependency_is_preserved_when_prerequisite_is_upstream(self):
        dependent = self.commit({"a.txt": "feature A\nB uses A\n"}, "dependent B")
        new_base = self.upstream(cherry=self.a)
        _, results = d.replay(self.repo, self.source, self.base, dependent, new_base)
        self.assertEqual(results[0]["status"], "upstream-equivalent")
        self.assertIn("B uses A", (self.source / "a.txt").read_text())

    def test_conflict_does_not_change_main_or_base(self):
        head = self.commit({"shared.txt": "local fix\n"}, "conflicting fix")
        new_base = self.upstream({"shared.txt": "upstream implementation\n"})
        with self.assertRaisesRegex(RuntimeError, "manual review"):
            d.replay(self.repo, self.source, self.base, head, new_base)
        self.assertEqual(d.git(self.repo, "rev-parse", "main"), head)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-base"), self.base)

    def test_non_equivalent_empty_patch_requires_review(self):
        # One upstream commit combines A with other work, so patch-id is not equivalent.
        new_base = self.upstream({"a.txt": "feature A\n", "other.txt": "different patch\n"})
        with self.assertRaisesRegex(RuntimeError, "manual review"):
            d.replay(self.repo, self.source, self.base, self.b, new_base)

    def test_rewind_rejected(self):
        with self.assertRaisesRegex(ValueError, "rewind"):
            d.replay(self.repo, self.source, self.a, self.b, self.base)

    def test_existing_destination_rejected(self):
        self.source.mkdir()
        (self.source / "keep").write_text("do not overwrite")
        with self.assertRaisesRegex(ValueError, "already exists"):
            d.replay(self.repo, self.source, self.base, self.b, self.base)
        self.assertTrue((self.source / "keep").exists())

    def test_merge_in_local_series_rejected(self):
        d.git(self.repo, "checkout", "-b", "side", self.base)
        side = self.commit({"side.txt": "side\n"}, "side")
        d.git(self.repo, "checkout", "main")
        d.git(self.repo, "merge", "--no-ff", "-m", "merge", side)
        with self.assertRaisesRegex(ValueError, "merges"):
            d.patch_series(self.repo, self.base, "HEAD")

    def test_stable_release_validation(self):
        self.assertEqual(d.stable_tag({"tag_name": "v2.22.1", "draft": False, "prerelease": False}), "v2.22.1")
        for release in ({"tag_name": "v2.0.0", "draft": True, "prerelease": False},
                        {"tag_name": "v2.0.0", "draft": False, "prerelease": True},
                        {"tag_name": "v2.0.0;touch /tmp/no", "draft": False, "prerelease": False},
                        {"tag_name": "v2.0.0-beta", "draft": False, "prerelease": False}, {}):
            with self.subTest(release=release), self.assertRaises(ValueError):
                d.stable_tag(release)

    def test_schedule_skips_already_published_source(self):
        d.git(self.repo, "push", "origin", f"{self.b}:refs/heads/downstream-published")
        plan = self.plan(event="schedule")
        self.assertFalse(plan["build"])
        self.assertFalse(self.source.exists())

    def test_schedule_retries_unpublished_main(self):
        plan = self.plan(event="schedule")
        self.assertTrue(plan["build"])
        self.assertEqual(plan["candidate"], self.b)

    def test_manual_run_rebuilds_without_upstream_change(self):
        d.git(self.repo, "push", "origin", f"{self.b}:refs/heads/downstream-published")
        self.assertTrue(self.plan(event="workflow_dispatch")["build"])

    def test_old_release_does_not_downgrade_newer_baseline(self):
        d.git(self.repo, "push", "origin", f"{self.a}:refs/heads/downstream-base")
        plan = self.plan()
        self.assertEqual(plan["base"], self.a)
        self.assertEqual(plan["candidate"], self.b)

    def test_packaging_keeps_tracked_source_unchanged(self):
        plan = self.plan()
        d.packaging(self.source, self.output)
        cfg = json.loads((self.output / "packaging.json").read_text())
        self.assertEqual(cfg["publish"][0]["owner"], "felixfoertsch")
        self.assertEqual(cfg["extraMetadata"]["version"], plan["version"])
        self.assertEqual(d.git(self.source, "status", "--porcelain"), "")

    def test_bundle_and_atomic_promotion(self):
        new_base = self.upstream()
        plan = self.plan(new_base)
        d.checksums(self.output)
        d.promote(self.repo, self.output, self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), plan["candidate"])
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-base"), new_base)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-published", False), "")
        self.assertEqual(d.remote_sha(self.repo, "refs/tags/downstream-backup/12345.1"), self.b)
        d.finish(self.repo, self.output)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-published"), plan["candidate"])

    def test_concurrent_push_is_not_overwritten(self):
        self.plan(self.upstream())
        d.checksums(self.output)
        concurrent = self.commit({"concurrent.txt": "user work\n"}, "user work during build")
        d.git(self.repo, "push", "origin", "main")
        with self.assertRaisesRegex(ValueError, "main advanced"):
            d.promote(self.repo, self.output, self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), concurrent)

    def test_server_rejection_is_atomic(self):
        self.plan(self.upstream())
        d.checksums(self.output)
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                        "  [ \"$ref\" = refs/heads/downstream-base ] && exit 1\n"
                        "done\nexit 0\n")
        hook.chmod(0o755)
        with self.assertRaises(RuntimeError):
            d.promote(self.repo, self.output, self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-base"), self.base)
        self.assertEqual(d.remote_sha(self.repo, "refs/tags/v2.0.0-felix.12345.1", False), "")

    def test_tampered_artifact_prevents_promotion(self):
        self.plan()
        d.checksums(self.output)
        (self.output / "build-info.json").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            d.promote(self.repo, self.output, self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.b)

    def test_unsafe_checksum_path_rejected(self):
        self.output.mkdir()
        (self.output / "SHA256SUMS").write_text("0" * 64 + "  ../escape\n")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            d.checksums(self.output, verify=True)

    def test_added_unchecksummed_file_rejected(self):
        self.plan()
        d.checksums(self.output)
        (self.output / "unexpected.txt").write_text("not verified")
        with self.assertRaisesRegex(ValueError, "Artifact set"):
            d.checksums(self.output, verify=True)

    def test_lease_catches_race_after_prechecks(self):
        self.plan(self.upstream())
        d.checksums(self.output)
        concurrent = self.commit({"concurrent.txt": "late user work\n"}, "concurrent push")
        def race(repo, *args, **kwargs):
            if args[0] == "push" and "--atomic" in args:
                self.real_git(self.repo, "push", "origin", "main")
            return self.real_git(repo, *args, **kwargs)
        with patch.object(d, "git", side_effect=race), self.assertRaises(RuntimeError):
            d.promote(self.repo, self.output, self.b)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), concurrent)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-base"), self.base)

    def test_health_snapshot_does_not_change_main(self):
        original_command = d.command
        def fake_issues(argv, **kwargs):
            return "[]" if argv[0] == "gh" else original_command(argv, **kwargs)
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_SHA": self.b,
                                      "BUILD_RESULT": "success", "PUBLISH_RESULT": "skipped"}), \
                patch.object(d, "command", side_effect=fake_issues):
            d.record_status(self.repo)
            first = d.remote_sha(self.repo, "refs/heads/downstream-status")
            d.record_status(self.repo)
            self.assertEqual(d.remote_sha(self.repo, "refs/heads/downstream-status"), first)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.b)

    def test_no_key_never_publishes_unsigned_pacman_package(self):
        self.output.mkdir()
        package = self.output / "heroic-felix.pkg.tar.zst"
        package.write_text("test package")
        result = subprocess.run(["bash", str(Path(__file__).with_name("sign.sh")), str(self.output)],
                                env={**os.environ, "PACMAN_SIGNING_KEY": "",
                                     "PACMAN_SIGNING_FINGERPRINT": "", "PACMAN_SIGNING_PASSPHRASE": ""},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(package.exists())
        self.assertTrue((self.output / "SIGNING-STATUS.txt").exists())

    def test_partial_signing_configuration_fails_closed(self):
        self.output.mkdir()
        result = subprocess.run(["bash", str(Path(__file__).with_name("sign.sh")), str(self.output)],
                                env={**os.environ, "PACMAN_SIGNING_KEY": "",
                                     "PACMAN_SIGNING_FINGERPRINT": "A" * 40,
                                     "PACMAN_SIGNING_PASSPHRASE": ""}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_unrelated_baseline_rejected(self):
        d.git(self.repo, "checkout", "--orphan", "unrelated")
        d.git(self.repo, "rm", "-rf", ".")
        other = self.commit({"another.txt": "other"}, "unrelated")
        with self.assertRaisesRegex(ValueError, "ancestor"):
            d.patch_series(self.repo, other, self.b)


if __name__ == "__main__":
    unittest.main()
