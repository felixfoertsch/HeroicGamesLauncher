"""A historical upstream patch does not imply its effect survived later reverts."""
import unittest

import downstream as d
import test_downstream as fixtures


class RevertedPatchTest(unittest.TestCase):
    def test_reverted_upstream_patch_is_reapplied(self):
        fixture = fixtures.DownstreamTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        included = fixture.upstream(cherry=fixture.a)
        d.git(fixture.repo, "checkout", "--detach", included)
        d.git(fixture.repo, "revert", "--no-edit", "HEAD")
        reverted = d.git(fixture.repo, "rev-parse", "HEAD")
        d.git(fixture.repo, "checkout", "main")
        _, results = d.replay(fixture.repo, fixture.source, fixture.base, fixture.b, reverted)
        self.assertEqual([p["status"] for p in results], ["replayed", "replayed"])
        self.assertEqual((fixture.source / "a.txt").read_text(), "feature A\n")


if __name__ == "__main__":
    unittest.main()
