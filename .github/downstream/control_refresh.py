"""Trusted control refresh. Prepared by Astra at Felix Förtsch's direction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from channel_build import compose_agents, reconstruct
from downstream import REPOSITORY, SHA, ancestor, command, git, outputs, remote_sha, write_json

UPSTREAM = 'https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher.git'
STATE = '.github/downstream/control_state.json'
UPSTREAM_REPOSITORY = 'Heroic-Games-Launcher/HeroicGamesLauncher'
UPSTREAM_REF = 'refs/heads/main'
OWNED = ('.github/downstream', '.github/workflows', '.mise.toml',
         'doc/downstream.md', 'doc/custom-builds.md')
SPECIAL = ('README.md', '.gitignore', 'AGENTS.md')
IGNORE = '__pycache__/\n*.pyc\n'


def owned(path):
    return path in SPECIAL or any(path == root or path.startswith(root + '/') for root in OWNED)


def selection(repo):
    info = json.loads(command(['gh', 'api', 'repos/Heroic-Games-Launcher/HeroicGamesLauncher']))
    branch = info['default_branch']
    state = json.loads((Path(repo) / STATE).read_text())
    if (info['full_name'] != state['repository'] or 'refs/heads/' + branch != state['ref']):
        raise ValueError('Upstream repository or default ref changed')
    git(repo, 'check-ref-format', 'refs/heads/' + branch)
    rows = git(repo, 'ls-remote', UPSTREAM, 'refs/heads/' + branch).splitlines()
    if len(rows) != 1 or not SHA.fullmatch(rows[0].split()[0]):
        raise ValueError('Cannot resolve upstream default branch')
    return branch, rows[0].split()[0]


def commit(repo, message, stamp):
    subprocess.run(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Heroic downstream',
                    '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    '-c', 'commit.gpgSign=false', 'commit', '-m', message,
                    '-m', 'Prepared by Astra, an OpenAI AI assistant, at Felix Förtsch’s direction.'],
                   env={**os.environ, 'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp},
                   check=True, capture_output=True)


def candidate(repo, source, upstream):
    repo, source = Path(repo).resolve(), Path(source).resolve()
    current = git(repo, 'rev-parse', 'HEAD')
    state = json.loads((repo / STATE).read_text())
    workflows = git(repo, 'ls-tree', '-r', '--name-only', current, '.github/workflows').splitlines()
    if workflows != ['.github/workflows/channel.yml']:
        raise ValueError('Only trusted channel workflow may be retained')
    base = state['base']
    if state.get('repository') != UPSTREAM_REPOSITORY or state.get('ref') != UPSTREAM_REF:
        raise ValueError('Unexpected upstream ownership metadata')
    if not SHA.fullmatch(upstream) or not SHA.fullmatch(base) or not ancestor(repo, base, upstream):
        raise ValueError('Invalid or rewound upstream')
    # Compare source with its declared reconstruction, never silently erase local customizations.
    with tempfile.TemporaryDirectory() as temp:
        previous = Path(temp) / 'previous'
        if state.get('legacy'):
            git(repo, 'worktree', 'add', '--detach', str(previous), base)
        else:
            reconstruct(repo, previous, base)
        expected = git(previous, 'rev-parse', 'HEAD')
        if not state.get('legacy'):
            compose_agents(repo, previous)
            if (previous / 'AGENTS.md').read_bytes() != (repo / 'AGENTS.md').read_bytes():
                raise ValueError('Unknown root AGENTS.md customization')
        paths = git(repo, 'diff', '--name-only', '-z', expected, current).split('\0')
        if any(path and not owned(path) for path in paths):
            raise ValueError('Unknown source customizations outside accepted queue')
        git(repo, 'worktree', 'remove', '--force', str(previous))
    for root in OWNED:
        for parent in Path(root).parents:
            if str(parent) != '.':
                entry = git(repo, 'ls-tree', upstream, '--', str(parent))
                if entry and not entry.startswith('040000 tree '):
                    raise ValueError('Upstream control parent collision: ' + str(parent))
        if root == '.github/workflows':
            continue
        if git(repo, 'ls-tree', upstream, '--', root):
            raise ValueError('Upstream control ownership collision: ' + root)
    # Only documented ignore additions belong to control; upstream entries stay fresh.
    old_ignore = git(repo, 'show', base + ':.gitignore')
    control_ignore = (repo / '.gitignore').read_text().strip()
    if state.get('legacy'):
        if control_ignore != old_ignore.replace('/coverage\n', '/coverage\n' + IGNORE):
            raise ValueError('Unknown ignore customization')
    elif control_ignore != old_ignore + '\n\n' + IGNORE.strip():
        raise ValueError('Unknown ignore customization')
    reconstruct(repo, source, upstream)
    for root in OWNED:
        target = source / root
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        origin = repo / root
        if origin.is_dir():
            shutil.copytree(origin, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        elif origin.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
    compose_agents(repo, source)
    prefix = (repo / 'README.md').read_text().split('\n---\n', 1)[0]
    (source / 'README.md').write_text(prefix + '\n---\n\n' + (source / 'README.md').read_text())
    (source / '.gitignore').write_text(git(repo, 'show', upstream + ':.gitignore') + '\n\n' + IGNORE)
    write_json(source / STATE, {'base': upstream, 'legacy': False,
                                'repository': state['repository'], 'ref': state['ref']})
    git(source, 'add', '-A')
    tree = git(source, 'write-tree')
    if tree == git(repo, 'rev-parse', current + '^{tree}') and ancestor(repo, upstream, current):
        return current
    commit(source, 'ci: Refresh upstream source and trusted control overlay', git(repo, 'show', '-s', '--format=%cI', upstream))
    result = git(source, 'rev-parse', 'HEAD')
    if git(repo, 'ls-tree', current, '.github/workflows') != git(repo, 'ls-tree', result, '.github/workflows'):
        raise ValueError('Control refresh changed workflow tree')
    return result


def backup(repo, destination, current):
    destination = Path(destination)
    ref = 'refs/control-backup/' + current
    git(repo, 'update-ref', ref, current)
    git(repo, 'bundle', 'create', str(destination), ref)
    verify_backup(destination, current)
    write_json(str(destination) + '.json', {'head': current, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()})


def verify_backup(bundle, current):
    with tempfile.TemporaryDirectory() as temp:
        command(['git', 'init', '--bare', temp])
        git(temp, 'bundle', 'verify', str(Path(bundle).resolve()))
        git(temp, 'fetch', str(Path(bundle).resolve()), current)
        if git(temp, 'rev-parse', 'FETCH_HEAD') != current:
            raise ValueError('Backup restored wrong control head')
        git(temp, 'fsck', '--full', '--no-dangling')


def promote(repo, result, current, branch, upstream, bundle, manifest, rebuild=False):
    data = json.loads(Path(manifest).read_text())
    if data != {'head': current, 'sha256': hashlib.sha256(Path(bundle).read_bytes()).hexdigest()}:
        raise ValueError('Backup hash mismatch')
    verify_backup(bundle, current)
    with tempfile.TemporaryDirectory() as temp:
        rebuilt = candidate(repo, Path(temp) / 'source', upstream)
        if rebuilt != result:
            raise ValueError('Untrusted refresh candidate')
    if result == current:
        return
    archive = 'refs/tags/archive/patch-queue/' + current
    archived = remote_sha(repo, archive, required=False)
    if archived and archived != current:
        raise ValueError('Archive tag does not point directly to old control')
    if selection(repo) != (branch, upstream) or remote_sha(repo, 'refs/heads/patch-queue') != current:
        raise ValueError('Upstream or control changed before refresh')
    args = ['push', '--atomic', '--force-with-lease=refs/heads/patch-queue:' + current]
    if not archived:
        args += ['--force-with-lease=' + archive + ':']
    args += ['origin', result + ':refs/heads/patch-queue']
    if not archived:
        args += [current + ':' + archive]
    git(repo, *args)
    # Existing tags cannot participate in a compare-only Git push. Verify both refs
    # again; privileged concurrent mutations remain outside this pre/post check.
    if (remote_sha(repo, 'refs/heads/patch-queue') != result
            or remote_sha(repo, archive) != current):
        raise ValueError('Control or archive changed after atomic refresh')
    # GITHUB_TOKEN pushes do not trigger push workflows. Failure leaves next schedule to recover.
    command(['gh', 'workflow', 'run', 'channel.yml', '--repo', REPOSITORY, '--ref', 'patch-queue',
             '-f', 'expected_control=' + result, '-f', 'rebuild=' + str(rebuild).lower()])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode', choices=['prepare', 'promote'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--rebuild', action='store_true')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    current = git('.', 'rev-parse', 'HEAD')
    if args.mode == 'prepare':
        output.mkdir()
        branch, upstream = selection('.')
        git('.', 'fetch', '--no-tags', UPSTREAM, upstream)
        with tempfile.TemporaryDirectory() as temp:
            result = candidate('.', Path(temp) / 'source', upstream)
        write_json(output / 'refresh.json', {'current': current, 'candidate': result, 'branch': branch, 'upstream': upstream})
        if result != current:
            backup('.', output / 'control.bundle', current)
        outputs({'changed': result != current})
    else:
        plan = json.loads((output / 'refresh.json').read_text())
        if plan['current'] != current:
            raise ValueError('Wrong trusted control checkout')
        git('.', 'fetch', '--no-tags', UPSTREAM, plan['upstream'])
        promote('.', plan['candidate'], current, plan['branch'], plan['upstream'],
                output / 'control.bundle', output / 'control.bundle.json', args.rebuild)


if __name__ == '__main__':
    main()
