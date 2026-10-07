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

    def test_queue_replays_without_original_commit_and_detects_applied_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / 'automation'
            d.command(['git', 'init', '-b', 'automation', str(repo)])
            (repo / 'package.json').write_text(json.dumps({'version': '2.0.0'}))
            (repo / 'README.md').write_text('Fork intro\n\n---\n\nUpstream README\n')
            (repo / 'game.txt').write_text('separate\n')
            d.git(repo, 'add', '.'); d.git(repo, 'commit', '-m', 'upstream')
            sidebar = repo / 'src/common/downstreamVersion.ts'
            sidebar.parent.mkdir(parents=True)
            sidebar.write_text('export const downstreamVersion = undefined\n')
            d.git(repo, 'add', '.'); d.git(repo, 'commit', '-m', 'sidebar')
            upstream = d.git(repo, 'rev-parse', 'HEAD')
            (repo / 'game.txt').write_text('stacked\n')
            d.git(repo, 'commit', '-am', 'feat: Stack games')
            mail = d.git(repo, 'format-patch', '-1', '--stdout')
            # Queue files are authoritative; their original commits need not exist.
            mail = mail.replace(d.git(repo, 'rev-parse', 'HEAD'), 'f' * 40, 1)
            d.git(repo, 'reset', '--hard', upstream)
            queue = repo / c.QUEUE; queue.mkdir(parents=True)
            (queue / '0001-stack.patch').write_text(mail + '\n')
            d.git(repo, 'add', '.'); d.git(repo, 'commit', '-m', 'queue')
            remote = root / 'origin.git'; d.command(['git', 'init', '--bare', str(remote)])
            d.git(repo, 'remote', 'add', 'origin', str(remote)); d.git(repo, 'push', 'origin', 'automation')
            plan = c.prepare(repo, root / 'source', root / 'output', upstream, 'v2.0.0', 'nightly', '123.1')
            self.assertEqual((root / 'source/game.txt').read_text(), 'stacked\n')
            self.assertEqual((root / 'source' / sidebar.relative_to(repo)).read_text(), "export const downstreamVersion = '2.0.0 + #1'\n")
            self.assertEqual(plan['patches'][0]['original'], 'f' * 40)
            self.assertEqual(plan['patches'][0]['subject'], 'feat: Stack games')
            self.assertEqual(plan['patches'][0]['status'], 'replayed')
            applied = plan['patches'][0]['commit']
            second = c.prepare(repo, root / 'second', root / 'second-output', applied, 'v2.0.0', 'stable', '123.1')
            self.assertEqual(second['patches'][0]['status'], 'upstream-equivalent')
            self.assertEqual(second['patches'][0]['commit'], applied)

    def test_stacking_queue_includes_regression_tests(self):
        repo = Path(__file__).parents[2]
        queue = c.patch_queue(repo)
        self.assertEqual([entry.name for entry in queue], ['0001-version-label.patch', '0002-stack-game-copies.patch', '0003-library-summary.patch', '0004-nile-session-recovery.patch'])
        self.assertIn('gameStack.test.ts', queue[1].read_text())

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
