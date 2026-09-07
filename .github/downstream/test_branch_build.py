"""Branch isolation, exact-source provenance, preview publication and CI-first regressions."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import branch_build as b
import downstream as d
from calver import FEED_URL, next_version, version_fields
from release_notes import render_notes


class IdentityTests(unittest.TestCase):
    def test_slash_case_punctuation_and_unicode_names_are_distinct(self):
        names = ["feat/stack", "feat-stack", "FEAT/stack", "feat/ä", "feat/ö", "feat/" + "a" * 200]
        values = [b.identity(name, "a" * 40, "123.1", "2.22.1") for name in names]
        self.assertEqual(len({v["tag"] for v in values}), len(names))
        for value in values:
            self.assertRegex(value["tag"], r"^preview-[a-z0-9.-]+$")
            self.assertLess(len(value["tag"]), 140)
            self.assertNotEqual(value["feedUrl"], FEED_URL)
            self.assertIn(value["tag"], value["feedUrl"])
            self.assertNotRegex(value["pacmanVersion"], r"[:/\s-]")

    def test_reserved_or_malformed_inputs_rejected(self):
        for name in [*b.INTERNAL_BRANCHES, "bad\nbranch", "../escape", "bad..branch", "bad branch"]:
            with self.subTest(name=name), self.assertRaises((ValueError, RuntimeError)):
                b.identity(name, "a" * 40, "123.1", "2.22.1")
        for sha, build, core in [("abc", "123.1", "2.22.1"), ("a" * 40, "001.2", "2.22.1"),
                                 ("a" * 40, "123.0", "2.22.1"), ("a" * 40, "123.1", "2.22.1-beta")]:
            with self.subTest(build=build), self.assertRaises(ValueError):
                b.identity("feature", sha, build, core)

    def test_source_and_attempt_are_unique(self):
        first = b.identity("feature", "a" * 40, "123.1", "2.22.1")
        self.assertNotEqual(first["tag"], b.identity("feature", "b" * 40, "123.1", "2.22.1")["tag"])
        self.assertNotEqual(first["tag"], b.identity("feature", "a" * 40, "123.2", "2.22.1")["tag"])
        self.assertIsNone(__import__('calver').RELEASE_TAG.fullmatch(first["tag"]))

    def test_preview_tags_do_not_consume_calver_counters(self):
        preview = b.identity("feature", "a" * 40, "123.1", "2.22.1")["tag"]
        self.assertEqual(next_version("v2.22.1", [preview]), next_version("v2.22.1", []))


class BranchGitTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"GITHUB_OUTPUT": os.devnull, "GITHUB_STEP_SUMMARY": os.devnull,
                                    "GITHUB_REPOSITORY": b.REPOSITORY})
        env.start(); self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.repo = self.root / "repo"
        self.remote = self.root / "origin.git"; self.out = self.root / "out"; self.source = self.root / "source"
        d.command(["git", "init", "-b", "main", str(self.repo)])
        d.command(["git", "init", "--bare", str(self.remote)])
        self.base = self.commit({"package.json": '{"version":"2.22.1"}\n'}, "upstream")
        self.ci = self.commit({"ci.txt": "automation\n"}, "ci: Builds\n\n" + b.CI_MARKER)
        d.git(self.repo, "remote", "add", "origin", str(self.remote))
        d.git(self.repo, "push", "origin", "main", f"{self.base}:refs/heads/downstream-base")
        d.git(self.repo, "checkout", "-b", "feat/stack")
        self.head = self.commit({"stack.txt": "stack\n"}, "feat: Stack all copies")
        d.git(self.repo, "push", "origin", "feat/stack")

    def commit(self, files, message):
        for name, value in files.items():
            (self.repo / name).write_text(value)
        d.git(self.repo, "add", "."); d.git(self.repo, "commit", "-m", message)
        return d.git(self.repo, "rev-parse", "HEAD")

    def prepare(self):
        return b.prepare(self.repo, self.source, self.out, "feat/stack", "123.1")

    def complete(self):
        plan = self.prepare(); b.packaging(self.source, self.out)
        for name in [f"Heroic-{plan['tag']}-custom-x86_64.AppImage", f"Heroic-{plan['tag']}-custom-x64.tar.xz",
                     f"heroic-felix-{plan['pacmanVersion']}-1-x86_64.pkg.tar.zst", "archlinux-image.txt"]:
            (self.out / name).write_bytes(b"fixture")
        b.write_feed(self.out); d.checksums(self.out)
        return plan

    def verify(self):
        return b.verify(self.repo, self.out, "feat/stack", self.head, "123.1")

    def test_exact_source_no_rebase_or_remote_mutation(self):
        plan = self.prepare()
        self.assertEqual(plan["candidate"], self.head)
        self.assertEqual(d.git(self.source, "rev-parse", "HEAD"), self.head)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.ci)
        self.assertEqual([p["commit"] for p in plan["patches"]], [self.ci, self.head])
        self.assertEqual(d.git(self.source, "status", "--porcelain"), "")

    def test_existing_destination_preserved(self):
        self.out.mkdir(); (self.out / "keep").write_text("data")
        with self.assertRaisesRegex(ValueError, "already exists"): self.prepare()
        self.assertTrue((self.out / "keep").exists())

    def test_missing_ci_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"): b.describe(self.repo, self.base)

    def test_multiple_ci_anchors_are_rejected(self):
        head = self.commit({"ci.txt": "new\n"}, "ci: incorrect second CI\n\n" + b.CI_MARKER)
        with self.assertRaisesRegex(ValueError, "exactly one"): b.describe(self.repo, head)

    def test_branch_pins_its_own_base_when_main_updates(self):
        d.git(self.repo, "checkout", "--detach", self.base)
        newer = self.commit({"upstream.txt": "new\n"}, "next upstream")
        d.git(self.repo, "push", "origin", f"{newer}:refs/heads/downstream-base")
        d.git(self.repo, "checkout", "feat/stack")
        self.assertEqual(self.prepare()["base"], self.base)

    def test_ci_stays_first_after_upstream_replay(self):
        d.git(self.repo, "checkout", "--detach", self.base)
        newer = self.commit({"upstream.txt": "new\n"}, "next upstream")
        candidate, _ = d.replay(self.repo, self.source, self.base, self.head, newer)
        description = b.describe(self.repo, candidate)
        self.assertEqual(description["base"], newer)
        self.assertEqual(description["patches"][0]["subject"], "ci: Builds")
        self.assertEqual(len(description["patches"]), 2)

    def test_packaging_and_feed_never_point_at_stable(self):
        plan = self.complete(); self.verify()
        config = json.loads((self.out / "packaging.json").read_text())
        self.assertEqual(config["publish"][0]["url"], plan["feedUrl"])
        self.assertNotEqual(config["publish"][0]["url"], FEED_URL)
        self.assertEqual(d.git(self.source, "status", "--porcelain"), "")

    def test_tampered_manifest_even_with_recomputed_checksums_is_rejected(self):
        self.complete()
        for key, value in [("branch", "other"), ("candidate", "f" * 40), ("buildId", "999.1"),
                           ("base", "c" * 40), ("patches", [])]:
            saved = (self.out / "build-info.json").read_text(); plan = json.loads(saved); plan[key] = value
            d.write_json(self.out / "build-info.json", plan); d.checksums(self.out)
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify()
            (self.out / "build-info.json").write_text(saved)

    def test_stable_feed_injection_rejected(self):
        self.complete(); path = self.out / "latest-linux.yml"
        info = json.loads(path.read_text()); info["path"] = FEED_URL + "/wrong.AppImage"
        d.write_json(path, info); d.checksums(self.out)
        with self.assertRaisesRegex(ValueError, "only its own"): self.verify()

    def test_missing_or_extra_assets_rejected(self):
        self.complete(); (self.out / "surprise.txt").write_text("unexpected"); d.checksums(self.out)
        with self.assertRaisesRegex(ValueError, "artifact set"): self.verify()
        (self.out / "surprise.txt").unlink(); next(self.out.glob("*.AppImage")).unlink(); d.checksums(self.out)
        with self.assertRaisesRegex(ValueError, "packages"): self.verify()

    def test_preview_release_is_draft_then_prerelease_never_latest(self):
        plan = self.complete(); calls = []
        def fake(args, **kwargs):
            calls.append(args); return ""
        with patch.object(b, "command", side_effect=fake):
            b.publish(self.repo, self.out, "feat/stack", self.head, "123.1")
        releases = [c for c in calls if c[:2] == ["gh", "release"]]
        self.assertEqual(len(releases), 2)
        self.assertIn("--draft", releases[0]); self.assertIn("--draft=false", releases[1])
        for c in releases:
            self.assertIn("--prerelease", c); self.assertIn("--latest=false", c)
            self.assertEqual(c[3], plan["tag"])
            self.assertNotIn("--clobber", c)
        self.assertEqual(d.remote_sha(self.repo, "refs/heads/main"), self.ci)

    def test_existing_preview_tag_is_never_overwritten(self):
        plan = self.complete()
        d.git(self.repo, "push", "origin", f"{self.head}:refs/tags/{plan['tag']}")
        with patch.object(b, "command") as publish, self.assertRaisesRegex(ValueError, "already exists"):
            b.publish(self.repo, self.out, "feat/stack", self.head, "123.1")
        self.assertFalse(any(c.args[0][:2] == ["gh", "release"] for c in publish.call_args_list))

    def test_main_release_notes_include_only_carried_commits_in_order(self):
        preview = self.prepare()
        plan = {**preview, **version_fields("v2.22.1", "2026.09.07", 1)}
        plan["patches"] = [{**p, "original": p["commit"], "status": "retained"} for p in preview["patches"]]
        plan["patches"].append({"original": "d" * 40, "subject": "fix: Already upstream", "status": "upstream-equivalent"})
        text = render_notes(plan)
        carried, supplied = text.split("### Already supplied by upstream")
        self.assertLess(carried.index("ci: Builds"), carried.index("feat: Stack all copies"))
        self.assertNotIn("Already upstream", carried); self.assertIn("Already upstream", supplied)
        self.assertNotIn("Recover Nile", text)
        self.assertIn(self.base, text); self.assertIn(self.head, text)


class WorkflowContractTests(unittest.TestCase):
    def test_all_branch_trigger_and_separate_preview_publisher(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/downstream.yml").read_text()
        self.assertIn("branches: ['**']", workflow)
        self.assertIn("format('heroic-preview-{0}', github.run_id)", workflow)
        publisher = workflow.split("  publish-preview:")[1].split("  status:")[0]
        self.assertIn("ref: main", publisher)
        self.assertNotIn("secrets.", publisher)
        self.assertIn("artifact-ids:", publisher)
        self.assertNotIn("promote --repo", publisher)
        self.assertIn("--branch \"$BRANCH\" --sha \"$EXPECTED_HEAD\"", publisher)


if __name__ == "__main__":
    unittest.main()
