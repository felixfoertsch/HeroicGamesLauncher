"""Real Git control-refresh regression checks, no network or personal identity."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import control_refresh as r
from downstream import command, git, write_json


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        command(['git', 'init', '-b', 'patch-queue', str(self.repo)])
        git(self.repo, 'config', 'maintenance.autoDetach', 'false')
        git(self.repo, 'config', 'gc.autoDetach', 'false')
        self.put('README.md', 'Complete upstream\n')
        self.put('.gitignore', 'ignored\n/coverage\n\n# production\n')
        self.put('game.txt', 'original\n')
        self.save('upstream')
        self.base = git(self.repo, 'rev-parse', 'HEAD')
        self.put('game.txt', 'accepted\n')
        self.save('accepted feature')
        mail = git(self.repo, 'format-patch', '-1', '--stdout') + '\n'
        git(self.repo, 'reset', '--hard', self.base)
        self.put('.github/downstream/patches/0001-game.patch', mail)
        self.put(r.STATE, json.dumps({'base': self.base, 'legacy': True, 'repository': r.UPSTREAM_REPOSITORY, 'ref': r.UPSTREAM_REF}))
        self.put('.github/workflows/channel.yml', 'trusted workflow\n')
        self.put('AGENTS.md', 'trusted agreement\n')
        self.put('.github/downstream/AGENTS.md', 'trusted agreement\n')
        self.put('.github/downstream/upstream-AGENTS.md', 'reviewed upstream policy\n')
        self.put('README.md', 'Fork prefix\n\n---\n\nComplete upstream\n')
        self.put('.gitignore', 'ignored\n/coverage\n' + r.IGNORE + '\n# production\n')
        self.save('control')
        self.current = git(self.repo, 'rev-parse', 'HEAD')
        self.remote = self.root / 'remote.git'
        command(['git', 'init', '--bare', str(self.remote)])
        git(self.remote, 'config', 'maintenance.autoDetach', 'false')
        git(self.remote, 'config', 'gc.autoDetach', 'false')
        git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        git(self.repo, 'push', 'origin', 'patch-queue')

    def put(self, path, value):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def save(self, message):
        git(self.repo, 'add', '-A')
        git(self.repo, '-c', 'commit.gpgSign=false', 'commit', '-m', message)

    def build(self, name='source', upstream=None):
        return r.candidate(self.repo, self.root / name, upstream or self.base)

    def test_replay_overlay_workflow_identity_determinism_and_noop(self):
        result = self.build()
        self.assertEqual(result, self.build('second'))
        source = self.root / 'source'
        self.assertEqual((source / 'game.txt').read_text(), 'accepted\n')
        self.assertEqual((source / 'README.md').read_text(), 'Fork prefix\n\n---\n\nComplete upstream\n')
        self.assertEqual(git(source, 'ls-tree', result, '.github/workflows'),
                         git(self.repo, 'ls-tree', self.current, '.github/workflows'))
        self.assertTrue((source / '.github/downstream/patches/0001-game.patch').is_file())
        git(self.repo, 'reset', '--hard', result)
        self.assertEqual(self.build('noop'), result)
        self.assertEqual(git(self.repo, 'merge-base', self.base, result), self.base)

    def test_unknown_customization_and_reserved_collision_stop(self):
        self.put('unknown.txt', 'never erase\n'); self.save('unknown')
        with self.assertRaisesRegex(ValueError, 'Unknown source'):
            self.build()
        git(self.repo, 'reset', '--hard', self.base)
        self.put('.mise.toml', 'new upstream owner\n'); self.save('collision')
        upstream = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', self.current)
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.build(upstream=upstream)

    def test_next_upstream_and_conflict_and_adoption(self):
        git(self.repo, 'reset', '--hard', self.base)
        self.put('README.md', 'New complete upstream\n'); self.save('upstream change')
        upstream = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', self.current)
        self.build(upstream=upstream)
        self.assertEqual((self.root / 'source/README.md').read_text(), 'Fork prefix\n\n---\n\nNew complete upstream\n')
        git(self.repo, 'reset', '--hard', upstream)
        self.put('game.txt', 'conflict\n'); self.save('conflict')
        conflict = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', self.current)
        with self.assertRaises(Exception):
            self.build('conflict', conflict)
        git(self.repo, 'reset', '--hard', upstream)
        self.put('game.txt', 'accepted\n'); self.save('adopted')
        adopted = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', self.current)
        self.build('adopted', adopted)
        self.assertEqual((self.root / 'adopted/game.txt').read_text(), 'accepted\n')

    def test_backup_restore_corruption_atomic_archive_and_dispatch_intent(self):
        result = self.build()
        bundle = self.root / 'backup.bundle'
        r.backup(self.repo, bundle, self.current)
        manifest = Path(str(bundle) + '.json')
        with patch.object(r, 'selection', return_value=('main', self.base)), patch.object(r, 'command', side_effect=lambda args, **kwargs: '' if args[:2] == ['gh', 'workflow'] else command(args, **kwargs)) as run:
            r.promote(self.repo, result, self.current, 'main', self.base, bundle, manifest, True)
            self.assertIn('rebuild=true', run.call_args.args[0])
            self.assertIn('expected_control=' + result, run.call_args.args[0])
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/patch-queue'), result)
        self.assertEqual(git(self.remote, 'cat-file', '-t', 'refs/tags/archive/patch-queue/' + self.current), 'commit')
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/tags/archive/patch-queue/' + self.current), self.current)
        bundle.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            r.promote(self.repo, result, self.current, 'main', self.base, bundle, manifest)

    def test_empty_upstream_commit_refreshes_once(self):
        result = self.build()
        git(self.repo, 'reset', '--hard', self.base)
        git(self.repo, '-c', 'commit.gpgSign=false', 'commit', '--allow-empty', '-m', 'empty upstream')
        upstream = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', result)
        refreshed = self.build('advanced', upstream)
        self.assertNotEqual(refreshed, result)
        self.assertEqual(git(self.repo, 'merge-base', upstream, refreshed), upstream)
        git(self.repo, 'reset', '--hard', refreshed)
        self.assertEqual(self.build('advanced-noop', upstream), refreshed)

    def test_prerequisite_bundle_rejected_and_dispatch_failure_leaves_recoverable_head(self):
        result = self.build()
        prerequisite = self.root / 'partial.bundle'
        git(self.repo, 'update-ref', 'refs/test-backup', self.current)
        git(self.repo, 'bundle', 'create', str(prerequisite), 'refs/test-backup', '^' + self.base)
        with self.assertRaises(RuntimeError):
            r.verify_backup(prerequisite, self.current)
        bundle = self.root / 'complete.bundle'; r.backup(self.repo, bundle, self.current)
        with patch.object(r, 'selection', return_value=('main', self.base)), patch.object(r, 'command', side_effect=lambda args, **kwargs: (_ for _ in ()).throw(RuntimeError('dispatch failed')) if args[:2] == ['gh', 'workflow'] else command(args, **kwargs)):
            with self.assertRaisesRegex(RuntimeError, 'dispatch failed'):
                r.promote(self.repo, result, self.current, 'main', self.base, bundle, str(bundle) + '.json')
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/patch-queue'), result)
        git(self.repo, 'reset', '--hard', result)
        self.assertEqual(self.build('recovery'), result)

    def test_reviewed_agents_composition_once_and_unknown_policy_stops(self):
        git(self.repo, 'reset', '--hard', self.base)
        self.put('AGENTS.md', 'reviewed upstream policy\n'); self.save('upstream guidance')
        upstream = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', self.current)
        result = self.build('composed', upstream)
        text = (self.root / 'composed/AGENTS.md').read_text()
        self.assertTrue(text.endswith('reviewed upstream policy\n'))
        self.assertEqual(text.count('trusted agreement'), 1)
        self.assertEqual(text.count('reviewed upstream policy'), 1)
        git(self.repo, 'reset', '--hard', result)
        self.assertEqual(self.build('composed-noop', upstream), result)
        git(self.repo, 'reset', '--hard', upstream)
        self.put('AGENTS.md', 'unreviewed restriction\n'); self.save('new policy')
        changed = git(self.repo, 'rev-parse', 'HEAD')
        git(self.repo, 'reset', '--hard', result)
        with self.assertRaisesRegex(ValueError, 'explicit policy review'):
            self.build('policy-change', changed)

    def test_atomic_control_lease_race_preserves_remote_and_creates_no_archive(self):
        result = self.build()
        bundle = self.root / 'race.bundle'; r.backup(self.repo, bundle, self.current)
        real_git = r.git
        def raced_git(repo, *args, **kwargs):
            if args[0] == 'push':
                real_git(self.remote, 'update-ref', 'refs/heads/patch-queue', self.base)
            return real_git(repo, *args, **kwargs)
        with patch.object(r, 'selection', return_value=('main', self.base)), patch.object(r, 'git', side_effect=raced_git):
            with self.assertRaises(RuntimeError):
                r.promote(self.repo, result, self.current, 'main', self.base, bundle, str(bundle) + '.json')
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/patch-queue'), self.base)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/tags/archive'), '')

    def test_promoter_rejects_untrusted_candidate_and_atomic_permission_failure(self):
        result = self.build()
        bundle = self.root / 'denied.bundle'; r.backup(self.repo, bundle, self.current)
        with self.assertRaisesRegex(ValueError, 'Untrusted refresh'):
            r.promote(self.repo, self.base, self.current, 'main', self.base, bundle, str(bundle) + '.json')
        git(self.remote, 'config', 'receive.denyNonFastForwards', 'true')
        with patch.object(r, 'selection', return_value=('main', self.base)):
            with self.assertRaises(RuntimeError):
                r.promote(self.repo, result, self.current, 'main', self.base, bundle, str(bundle) + '.json')
        self.assertEqual(git(self.remote, 'rev-parse', 'refs/heads/patch-queue'), self.current)
        self.assertEqual(git(self.remote, 'for-each-ref', '--format=%(refname)', 'refs/tags/archive'), '')

    def test_post_push_ref_mutations_prevent_dispatch(self):
        result = self.build()
        bundle = self.root / 'post-push.bundle'; r.backup(self.repo, bundle, self.current)
        archive = 'refs/tags/archive/patch-queue/' + self.current
        real_git = r.git
        for target, value in [(archive, self.base), (archive, None),
                              ('refs/heads/patch-queue', self.base), ('refs/heads/patch-queue', None)]:
            with self.subTest(target=target, value=value):
                real_git(self.remote, 'update-ref', 'refs/heads/patch-queue', self.current)
                real_git(self.remote, 'update-ref', '-d', archive)
                def mutate_after_push(repo, *args, **kwargs):
                    answer = real_git(repo, *args, **kwargs)
                    if args[0] == 'push':
                        if value is None:
                            real_git(self.remote, 'update-ref', '-d', target)
                        else:
                            real_git(self.remote, 'update-ref', target, value)
                    return answer
                with patch.object(r, 'selection', return_value=('main', self.base)), patch.object(r, 'git', side_effect=mutate_after_push), patch.object(r, 'command', wraps=command) as run:
                    with self.assertRaises((ValueError, RuntimeError)):
                        r.promote(self.repo, result, self.current, 'main', self.base, bundle, str(bundle) + '.json')
                    self.assertFalse(any(call.args[0][:2] == ['gh', 'workflow'] for call in run.call_args_list))

    def test_post_push_read_failure_prevents_dispatch(self):
        result = self.build()
        bundle = self.root / 'read-failure.bundle'; r.backup(self.repo, bundle, self.current)
        real_git = r.git
        pushed = False
        def track_push(repo, *args, **kwargs):
            nonlocal pushed
            answer = real_git(repo, *args, **kwargs)
            if args[0] == 'push':
                pushed = True
            return answer
        real_remote = r.remote_sha
        def failed_read(repo, name, required=True):
            if pushed:
                raise RuntimeError('post-push read failed')
            return real_remote(repo, name, required)
        with patch.object(r, 'selection', return_value=('main', self.base)), patch.object(r, 'git', side_effect=track_push), patch.object(r, 'remote_sha', side_effect=failed_read), patch.object(r, 'command', wraps=command) as run:
            with self.assertRaisesRegex(RuntimeError, 'post-push read failed'):
                r.promote(self.repo, result, self.current, 'main', self.base, bundle, str(bundle) + '.json')
            self.assertFalse(any(call.args[0][:2] == ['gh', 'workflow'] for call in run.call_args_list))

    def test_credential_steps_use_writable_isolated_git_config(self):
        workflow = (Path(__file__).parents[1] / 'workflows/channel.yml').read_text()
        self.assertIn("GIT_CONFIG_GLOBAL: /dev/null", workflow)
        self.assertEqual(workflow.count('GIT_CONFIG_GLOBAL: ${{ runner.temp }}/heroic-trusted-gitconfig'), 2)
        for block in workflow.split('\n      - '):
            if 'gh auth setup-git' in block:
                self.assertIn('GIT_CONFIG_GLOBAL: ${{ runner.temp }}/heroic-trusted-gitconfig', block)

    def test_archive_namespace_excluded_from_release_selectors(self):
        from calver import RELEASE_TAG, next_version
        from release_cleanup import LEGACY_TAG
        archive = 'archive/patch-queue/' + self.current
        self.assertIsNone(RELEASE_TAG.fullmatch(archive))
        self.assertIsNone(LEGACY_TAG.fullmatch(archive))
        self.assertEqual(next_version('v2.0.0', [archive]), next_version('v2.0.0', []))

    def test_stale_control_and_wrong_archive_stop(self):
        result = self.build()
        bundle = self.root / 'backup.bundle'; r.backup(self.repo, bundle, self.current)
        manifest = Path(str(bundle) + '.json')
        archive = 'refs/tags/archive/patch-queue/' + self.current
        git(self.remote, 'update-ref', archive, self.base)
        with self.assertRaisesRegex(ValueError, 'Archive tag'):
            r.promote(self.repo, result, self.current, 'main', self.base, bundle, manifest)
        git(self.remote, 'update-ref', archive, self.current)
        with patch.object(r, 'selection', return_value=('other', self.base)):
            with self.assertRaisesRegex(ValueError, 'changed before'):
                r.promote(self.repo, result, self.current, 'main', self.base, bundle, manifest)


if __name__ == '__main__':
    unittest.main()
