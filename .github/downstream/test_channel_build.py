import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import channel_build as c
import downstream as d


class ChannelBuildTests(unittest.TestCase):
    def test_generated_nightly_removes_workflows_and_keeps_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / "patch-queue"; source = root / "source"; output = root / "output"
            d.command(["git", "init", "-b", "patch-queue", str(repo)])
            (repo / "package.json").write_text(json.dumps({"version": "2.0.0"}))
            (repo / 'README.md').write_text('Fork intro\n\n# Downstream patches\n\nNone accepted.\n\n---\n\nUpstream README\n')
            (repo / ".github/workflows").mkdir(parents=True); (repo / ".github/workflows/ci.yml").write_text("on: push\n")
            (repo / ".github/downstream").mkdir(parents=True); (repo / ".github/downstream/tool.py").write_text("trusted")
            d.git(repo, "add", "."); d.git(repo, "commit", "-m", "patch-queue")
            upstream = d.git(repo, "rev-parse", "HEAD")
            remote = root / "origin.git"; d.command(["git", "init", "--bare", str(remote)])
            d.git(repo, "remote", "add", "origin", str(remote)); d.git(repo, "push", "origin", "patch-queue")
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
            with patch.object(c, 'published_candidate', return_value=True):
                skipped = c.prepare(repo, root / 'skipped', root / 'skipped-output', upstream,
                                    'v2.0.0', 'nightly', '123.1', skip_published=True)
            self.assertFalse(skipped['build'])
            self.assertFalse((root / 'skipped-output').exists())
            with patch.object(c, 'git', return_value='different-upstream'):
                with self.assertRaisesRegex(ValueError, 'Upstream changed'):
                    c.freshness(repo, plan)
            d.git(repo, 'commit', '--allow-empty', '-m', 'queue changed')
            d.git(repo, 'push', 'origin', 'patch-queue')
            with self.assertRaisesRegex(ValueError, 'Patch queue changed'):
                c.freshness(repo, plan)
            plan['version'] = '2.0.0'
            with self.assertRaises(ValueError):
                c.validate_plan_version(plan)

    def test_queue_replays_without_original_commit_and_detects_applied_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / 'patch-queue'
            d.command(['git', 'init', '-b', 'patch-queue', str(repo)])
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
            d.git(repo, 'remote', 'add', 'origin', str(remote)); d.git(repo, 'push', 'origin', 'patch-queue')
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

    def test_published_candidate_skips_only_complete_matching_release(self):
        import hashlib
        plan = {'candidate': 'a' * 40, 'base': 'b' * 40, 'expectedAutomation': 'c' * 40,
                'channel': 'stable', 'upstream': {'tag': 'v2.0.0', 'sha': 'b' * 40},
                'passedChecks': c.CHECKS}
        from calver import version_fields
        plan.update(version_fields('v2.0.0', '2026.10.08', 1))
        plan.update({'schema': 2, 'repository': c.REPOSITORY})
        manifest = json.dumps(plan)
        names = ['build-info.json', 'packaging.json', 'RELEASE-NOTES.md', 'latest-linux.yml',
                 'archlinux-image.txt', f"Heroic-{plan['tag']}-source.tar.gz",
                 f"Heroic-{plan['tag']}-linux-x86_64.AppImage", f"Heroic-{plan['tag']}-linux-x64.tar.xz",
                 'SIGNING-STATUS.txt']
        assets = [{'name': name, 'digest': 'sha256:' + hashlib.sha256(
            manifest.encode() if name == 'build-info.json' else b'fixture').hexdigest()} for name in names]
        sums = ''.join(f"{asset['digest'][7:]}  {asset['name']}\n" for asset in assets)
        assets.append({'name': 'SHA256SUMS', 'digest': 'sha256:' + hashlib.sha256(sums.encode()).hexdigest()})
        release = {'tag_name': plan['tag'], 'draft': False, 'prerelease': False, 'assets': assets}
        def run(args):
            if args[:3] == ['gh', 'api', 'repos/' + c.REPOSITORY + '/releases?per_page=100']:
                return json.dumps([[release, {'tag_name': 'downstream-feed', 'draft': False, 'prerelease': True,
                    'assets': [asset for asset in release['assets'] if asset['name'] == 'latest-linux.yml']} ]])
            destination = Path(args[args.index('--dir') + 1])
            (destination / 'build-info.json').write_text(manifest)
            (destination / 'SHA256SUMS').write_text(sums)
            return ''
        with patch.object(c, 'command', side_effect=run), patch.object(c, 'remote_sha', return_value=plan['candidate']):
            self.assertTrue(c.published_candidate(plan))
            with patch.object(c, 'remote_sha', return_value=plan['candidate']) as remote:
                self.assertTrue(c.published_candidate(plan, '/different/repo'))
                remote.assert_called_with('/different/repo', 'refs/tags/' + plan['tag'])
            package = f"heroic-games-launcher-bin-{plan['pacmanVersion']}-1-x86_64.pkg.tar.zst"
            release['assets'].append({'name': package + '.sig', 'digest': 'sha256:' + '0' * 64})
            self.assertFalse(c.published_candidate(plan))
            release['assets'].pop()
            with patch.object(c, 'remote_sha', return_value='e' * 40):
                with self.assertRaisesRegex(ValueError, 'tag source mismatch'):
                    c.published_candidate(plan)
            release['tag_name'] = 'wrong-tag'
            with self.assertRaisesRegex(ValueError, 'tag source mismatch'):
                c.published_candidate(plan)
            release['tag_name'] = plan['tag']
            with patch.object(c, 'command', side_effect=lambda args: json.dumps([[release]]) if args[1] == 'api' else run(args)):
                self.assertFalse(c.published_candidate(plan))
            self.assertFalse(c.published_candidate({**plan, 'expectedAutomation': 'd' * 40}))
            removed = release['assets'].pop(1)
            self.assertFalse(c.published_candidate(plan))
            release['assets'].insert(1, removed)
            release['draft'] = True
            self.assertFalse(c.published_candidate(plan))
            release['draft'] = False
            release['assets'][0]['digest'] = 'sha256:' + '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                c.published_candidate(plan)

    def test_readme_links_each_patch_on_control_branch(self):
        repo = Path(__file__).parents[2]
        readme = (repo / 'README.md').read_text()
        paragraph = readme.split('\n\n', 1)[0]
        for entry in c.patch_queue(repo):
            link = f'https://github.com/{c.REPOSITORY}/blob/patch-queue/{c.QUEUE}/{entry.name}'
            self.assertIn(f'[{entry.name[:4]}]({link})', paragraph)
            self.assertIn(link, readme.split('\n---\n', 1)[0])

    def test_packages_keep_upstream_names(self):
        repo = Path(__file__).parents[2]
        recipe = (repo / '.github/downstream/PKGBUILD').read_text()
        self.assertIn('pkgname=heroic-games-launcher-bin', recipe)
        self.assertIn('Name=Heroic Games Launcher\n', recipe)
        self.assertNotIn('Name=Custom Heroic', recipe)
        self.assertNotIn('Name=Heroic Games Launcher (Felix)', recipe)
        for filename in ('downstream.py', 'branch_build.py'):
            self.assertIn('-linux-${arch}.${ext}', (repo / '.github/downstream' / filename).read_text())

    def test_channel_workflow_retains_full_build_and_trust_guards(self):
        workflows = Path(__file__).parents[1] / 'workflows'
        self.assertEqual(sorted(path.name for path in workflows.iterdir()), ['channel.yml'])
        workflow = (workflows / 'channel.yml').read_text()
        for contract in ('pnpm install --frozen-lockfile', 'pnpm codecheck', 'pnpm test --runInBand',
                         'pnpm lint', 'pnpm prettier', '--linux AppImage tar.xz',
                         'makepkg --nodeps', 'pacman --config', 'digest-mismatch: error',
                         'passedChecks', "matrix.channel == 'stable'", 'persist-credentials: false'):
            self.assertIn(contract, workflow)
        self.assertNotIn('DOWNSTREAM_PUSH_TOKEN', workflow)
        self.assertIn('branches: [patch-queue]', workflow)
        self.assertEqual(workflow.count("github.ref == 'refs/heads/patch-queue'"), 2)
        self.assertIn('--patch-queue-sha', workflow)
        self.assertNotIn('refs/heads/automation', workflow)


if __name__ == "__main__":
    unittest.main()
