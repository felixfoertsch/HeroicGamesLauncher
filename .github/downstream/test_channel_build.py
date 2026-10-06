import json
from pathlib import Path
import tempfile
import unittest

import channel_build as c
import downstream as d


class ChannelBuildTests(unittest.TestCase):
    def test_generated_nightly_removes_workflows_and_keeps_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / "automation"; source = root / "source"; output = root / "output"
            d.command(["git", "init", "-b", "automation", str(repo)])
            (repo / "package.json").write_text(json.dumps({"version": "2.0.0"}))
            (repo / 'README.md').write_text('Fork intro\n\n# Downstream patches\n\nNone accepted.\n\n---\n\nUpstream README\n')
            (repo / ".github/workflows").mkdir(parents=True); (repo / ".github/workflows/ci.yml").write_text("on: push\n")
            (repo / ".github/downstream").mkdir(parents=True); (repo / ".github/downstream/tool.py").write_text("trusted")
            d.git(repo, "add", "."); d.git(repo, "commit", "-m", "automation")
            upstream = d.git(repo, "rev-parse", "HEAD")
            remote = root / "origin.git"; d.command(["git", "init", "--bare", str(remote)])
            d.git(repo, "remote", "add", "origin", str(remote)); d.git(repo, "push", "origin", "automation")
            plan = c.prepare(repo, source, output, upstream, "v2.0.0", "nightly", "123.1")
            self.assertEqual(plan["channel"], "nightly")
            self.assertFalse((source / ".github/workflows").exists())
            self.assertTrue((source / ".github/downstream/tool.py").is_file())
            c.validate_plan_version(plan)
            self.assertTrue(plan['tag'].startswith('nightly-'))
            self.assertEqual(plan['patches'], [])
            self.assertIn('Upstream README', (source / 'README.md').read_text())
            second = c.prepare(repo, root / 'second', root / 'second-output', upstream, 'v2.0.0', 'nightly', '123.1')
            self.assertEqual(plan['candidate'], second['candidate'])
            plan['version'] = '2.0.0'
            with self.assertRaises(ValueError):
                c.validate_plan_version(plan)

    def test_channel_workflow_retains_full_build_and_trust_guards(self):
        workflow = (Path(__file__).parents[1] / 'workflows/channel.yml').read_text()
        for contract in ('pnpm install --frozen-lockfile', 'pnpm codecheck', 'pnpm test --runInBand',
                         'pnpm lint', 'pnpm prettier', '--linux AppImage tar.xz',
                         'makepkg --nodeps', 'pacman --config', 'digest-mismatch: error',
                         'passedChecks', 'matrix.channel == \'stable\'', 'persist-credentials: false'):
            self.assertIn(contract, workflow)
        self.assertNotIn('DOWNSTREAM_PUSH_TOKEN', workflow)


if __name__ == "__main__":
    unittest.main()
