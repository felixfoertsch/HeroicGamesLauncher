"""Prepare stable and nightly candidates from patch-queue's ordered patches."""
import argparse
from email import policy
from email.parser import Parser
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import base64
import hashlib
from urllib.parse import quote

from calver import next_version
from downstream import REPOSITORY, SHA, checksums, command, git, outputs, remote_sha, write_json
from calver import validate_plan_version
from release_notes import render_notes
import os

CHECKS = ['typescript', 'jest', 'eslint', 'prettier', 'linux-packaging', 'arch-package', 'pacman-smoke']

QUEUE = Path(".github/downstream/patches")
COPIED = (".github/downstream", "doc/downstream.md", "AGENTS.md", ".mise.toml")


def patch_queue(repo):
    directory = Path(repo) / QUEUE
    if not directory.exists():
        return []
    patches = sorted(directory.glob("[0-9][0-9][0-9][0-9]-*.patch"))
    if len(patches) != len(list(directory.iterdir())):
        raise ValueError("Patch queue contains an invalid entry")
    return patches


def published_candidate(plan, repo='.'):
    pages = json.loads(command(['gh', 'api', f'repos/{REPOSITORY}/releases?per_page=100', '--paginate', '--slurp']))
    for release in (release for page in pages for release in page):
        if release['draft'] or release['prerelease'] != (plan['channel'] == 'nightly'):
            continue
        assets = {asset['name']: asset for asset in release['assets']}
        if not {'build-info.json', 'SHA256SUMS'} <= assets.keys():
            continue
        with tempfile.TemporaryDirectory() as temp:
            command(['gh', 'release', 'download', release['tag_name'], '--repo', REPOSITORY,
                     '--pattern', 'build-info.json', '--pattern', 'SHA256SUMS', '--dir', temp])
            for name in ('build-info.json', 'SHA256SUMS'):
                digest = 'sha256:' + hashlib.sha256((Path(temp) / name).read_bytes()).hexdigest()
                if assets[name].get('digest') != digest:
                    raise ValueError('Published provenance hash mismatch')
            previous = json.loads((Path(temp) / 'build-info.json').read_text())
            if any(previous.get(key) != plan.get(key) for key in
                   ('candidate', 'base', 'expectedAutomation', 'channel', 'upstream')):
                continue
            if previous.get('passedChecks') != CHECKS or previous.get('repository') != REPOSITORY or previous.get('schema') != 2:
                continue
            validate_plan_version(previous)
            tag = previous['tag']
            if tag != release['tag_name'] or remote_sha(repo, 'refs/tags/' + tag) != previous['candidate']:
                raise ValueError('Published tag source mismatch')
            required = {'build-info.json', 'SHA256SUMS', 'packaging.json', 'RELEASE-NOTES.md',
                        'latest-linux.yml', 'archlinux-image.txt', f'Heroic-{tag}-source.tar.gz',
                        f'Heroic-{tag}-linux-x86_64.AppImage', f'Heroic-{tag}-linux-x64.tar.xz'}
            package = f"heroic-games-launcher-bin-{previous['pacmanVersion']}-1-x86_64.pkg.tar.zst"
            if plan['channel'] == 'nightly' or package in assets:
                required.add(package)
            if plan['channel'] == 'stable':
                if package + '.sig' in assets:
                    required.update({package, package + '.sig', 'heroic-games-launcher-bin-key.asc',
                                     'heroic-games-launcher-bin-key.fingerprint', 'heroic-games-launcher-bin.db',
                                     'heroic-games-launcher-bin.db.sig', 'heroic-games-launcher-bin.files',
                                     'heroic-games-launcher-bin.files.sig'})
                else:
                    required.add('SIGNING-STATUS.txt')
            if set(assets) != required:
                return False
            rows = (Path(temp) / 'SHA256SUMS').read_text().splitlines()
            recorded = dict((name, 'sha256:' + digest) for digest, name in
                            (row.split('  ', 1) for row in rows))
            complete = (set(recorded) == set(assets) - {'SHA256SUMS'} and
                        all(assets[name].get('digest') == digest for name, digest in recorded.items()))
            if not complete:
                continue
            if plan['channel'] == 'stable':
                for delivery, names in [('downstream-feed', {'latest-linux.yml'}),
                                        ('pacman', {name for name in assets if name.startswith('heroic-games-launcher-bin')})]:
                    if delivery == 'pacman' and package + '.sig' not in assets:
                        continue
                    feed = next((entry for page in pages for entry in page
                                 if entry['tag_name'] == delivery and not entry['draft']), None)
                    delivery_assets = {asset['name']: asset for asset in feed['assets']} if feed else {}
                    if any(delivery_assets.get(name, {}).get('digest') != assets[name].get('digest') for name in names):
                        return False
            return True
    return False


def prepare(repo, source, output, upstream_sha, upstream_tag, channel, build_id, skip_published=False):
    repo, source, output = (Path(value).resolve() for value in (repo, source, output))
    if source.exists() or output.exists() or not SHA.fullmatch(upstream_sha):
        raise ValueError("Invalid candidate destination or upstream SHA")
    if channel not in {"stable", "nightly"} or not re.fullmatch(r"v?\d+\.\d+\.\d+", upstream_tag):
        raise ValueError("Invalid channel upstream version")
    git(repo, "worktree", "add", "--detach", str(source), upstream_sha)
    patches = []
    for patch in patch_queue(repo):
        first = patch.read_text().splitlines()[0:1]
        if not first or not re.fullmatch(r"From [0-9a-f]{40} .*", first[0]):
            raise ValueError(f"Patch lacks immutable source SHA: {patch.name}")
        original = first[0].split()[1]
        message = Parser(policy=policy.default).parsestr(patch.read_text())
        subject = re.sub(r'^\[PATCH[^\]]*\]\s*', '', str(message['Subject'] or ''))
        if not subject or any(character in subject for character in '\r\n'):
            raise ValueError(f"Patch lacks a valid subject: {patch.name}")
        reverse = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=source,
                                             text=True, capture_output=True)
        status = 'upstream-equivalent' if reverse.returncode == 0 else 'replayed'
        if status == 'replayed':
            stamp = git(repo, 'show', '-s', '--format=%cI', 'HEAD')
            subprocess.run(['git', '-c', 'user.name=Astra', '-c', 'user.email=astra@users.noreply.github.com',
                            '-c', 'commit.gpgSign=false', 'am', '--keep-non-patch', str(patch)],
                           cwd=source, env={**os.environ, 'GIT_COMMITTER_DATE': stamp},
                           check=True, capture_output=True)
        patches.append({"original": original, "commit": git(source, "rev-parse", "HEAD"),
                        "subject": subject, "status": status})
    # Display upstream identity separately from CalVer used by package updates.
    display = source / 'src/common/downstreamVersion.ts'
    if display.exists():
        upstream_version = json.loads((source / 'package.json').read_text())['version']
        if not re.fullmatch(r'[0-9A-Za-z.+-]+', upstream_version):
            raise ValueError('Invalid upstream package version')
        label = repr(f'{upstream_version} + #{len(patches)}')
        display.write_text(f'export const downstreamVersion = {label}\n')
    readme = (source / 'README.md').read_text()
    introduction = (repo / 'README.md').read_text().split('\n---\n', 1)[0]
    (source / 'README.md').write_text(introduction + '\n---\n\n' + readme)
    shutil.rmtree(source / ".github/workflows", ignore_errors=True)
    for relative in COPIED:
        origin, target = repo / relative, source / relative
        if origin.is_dir():
            shutil.copytree(origin, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("patches", "__pycache__", "*.pyc"))
        elif origin.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
    git(source, "add", "-A")
    if git(source, "status", "--porcelain"):
        stamp = git(repo, 'show', '-s', '--format=%cI', 'HEAD')
        env = {**os.environ, 'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp}
        subprocess.run(['git', '-c', 'user.name=Astra', '-c', 'user.email=astra@users.noreply.github.com',
                        'commit', '--no-gpg-sign', '-m', 'ci: retain trusted downstream tooling',
                        '-m', 'Prepared by Astra, an OpenAI AI assistant, at Felix Förtsch’s direction.'],
                       cwd=source, env=env, check=True, capture_output=True)
    candidate = git(source, "rev-parse", "HEAD")
    if git(source, "ls-files", ".github/workflows"):
        raise ValueError("Generated main candidate contains workflow files")
    tags = [line.split()[1].removeprefix("refs/tags/") for line in git(repo, "ls-remote", "--tags", "--refs", "origin").splitlines()]
    version = next_version(upstream_tag, tags)
    if not re.fullmatch(r'[1-9]\d*\.[1-9]\d*', build_id):
        raise ValueError('Invalid build identity')
    if channel == 'nightly':
        version['tag'] = 'nightly-' + version['tag'] + '-' + build_id
        version['version'] += '.nightly.' + build_id
        version['pacmanVersion'] += '.nightly.' + build_id
    # Keep expectedAutomation in schema 2 for existing release provenance.
    plan = {"schema": 2, "repository": REPOSITORY, "channel": channel, "candidate": candidate,
            "base": upstream_sha, "upstream": {"tag": upstream_tag, "sha": upstream_sha},
            "expectedMain": remote_sha(repo, 'refs/heads/main', required=False),
            "expectedAutomation": git(repo, 'rev-parse', 'HEAD'),
            "packageManager": json.loads((source / 'package.json').read_text()).get('packageManager'),
            "build": True, "patches": patches, "buildId": build_id, **version}
    if skip_published and published_candidate({**plan, 'passedChecks': CHECKS}, repo):
        outputs({'build': False})
        return {**plan, 'build': False}
    output.mkdir(parents=True)
    write_json(output / "build-info.json", plan)
    git(repo, "update-ref", "refs/downstream-candidate", candidate)
    git(repo, "bundle", "create", str(output / "source.bundle"), "refs/downstream-candidate", f"^{upstream_sha}")
    git(repo, "archive", "--format=tar.gz", f"--prefix=Heroic-{plan['tag']}/", f"--output={output / ('Heroic-' + plan['tag'] + '-source.tar.gz')}", candidate)
    outputs({"build": True, "candidate": candidate, "tag": plan["tag"], "version": plan["version"],
             "pacman_version": plan["pacmanVersion"], "pacman_release": plan["pacmanRelease"]})
    return plan


def verify(repo, output, channel, build_id, patch_queue_sha, signed=False):
    output = Path(output)
    checksums(output, verify=True)
    plan = json.loads((output / 'build-info.json').read_text())
    validate_plan_version(plan)
    if (plan.get('schema') != 2 or plan.get('repository') != REPOSITORY
            or plan.get('channel') != channel or plan.get('buildId') != build_id
            or plan.get('expectedAutomation') != patch_queue_sha or plan.get('passedChecks') != CHECKS):
        raise ValueError('Unexpected channel provenance or incomplete validation')
    for key in ('candidate', 'base', 'expectedAutomation'):
        if not SHA.fullmatch(plan.get(key, '')):
            raise ValueError('Invalid source identity')
    required = {'build-info.json', 'source.bundle', 'packaging.json', 'RELEASE-NOTES.md',
                'latest-linux.yml', 'archlinux-image.txt', 'SHA256SUMS',
                f"Heroic-{plan['tag']}-source.tar.gz"}
    patterns = [f"Heroic-{plan['tag']}-linux-*.AppImage", f"Heroic-{plan['tag']}-linux-*.tar.xz"]
    package = f"heroic-games-launcher-bin-{plan['pacmanVersion']}-1-x86_64.pkg.tar.zst"
    if not signed or os.environ.get('SIGNED') == 'true':
        patterns.append(package)
    if signed:
        if os.environ.get('SIGNED') == 'true':
            required.update({package + '.sig', 'heroic-games-launcher-bin.db', 'heroic-games-launcher-bin.db.sig',
                             'heroic-games-launcher-bin.files', 'heroic-games-launcher-bin.files.sig',
                             'heroic-games-launcher-bin-key.asc', 'heroic-games-launcher-bin-key.fingerprint'})
        else:
            required.add('SIGNING-STATUS.txt')
    for pattern in patterns:
        matches = list(output.glob(pattern))
        if len(matches) != 1:
            raise ValueError('Incomplete channel packages')
        required.add(matches[0].name)
    if required != {p.name for p in output.iterdir()}:
        raise ValueError('Unexpected artifact set')
    git(repo, 'fetch', '--no-tags', 'https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher.git', plan['base'])
    git(repo, 'bundle', 'verify', str(output / 'source.bundle'))
    git(repo, 'fetch', str(output / 'source.bundle'), 'refs/downstream-candidate:refs/downstream-promote')
    if git(repo, 'rev-parse', 'refs/downstream-promote') != plan['candidate']:
        raise ValueError('Bundle source differs from validated candidate')
    if git(repo, 'ls-tree', '-r', '--name-only', plan['candidate'], '.github/workflows'):
        raise ValueError('Generated source contains workflows')
    with tempfile.TemporaryDirectory() as temp:
        rebuilt = prepare(repo, Path(temp) / 'source', Path(temp) / 'release', plan['base'],
                          plan['upstream']['tag'], channel, build_id)
        for key in ('candidate', 'patches', 'packageManager'):
            if rebuilt[key] != plan[key]:
                raise ValueError('Source differs from trusted patch reconstruction')
    image = next(output.glob(f"Heroic-{plan['tag']}-linux-*.AppImage"))
    with image.open('rb') as stream:
        digest = base64.b64encode(hashlib.file_digest(stream, 'sha512').digest()).decode('ascii')
    url = f"https://github.com/{REPOSITORY}/releases/download/{plan['tag']}/{quote(image.name)}"
    feed = json.loads((output / 'latest-linux.yml').read_text())
    if (feed.get('version') != plan['version'] or feed.get('releaseName') != plan['tag']
            or feed.get('path') != url or feed.get('sha512') != digest
            or feed.get('files') != [{'url': url, 'sha512': digest, 'size': image.stat().st_size}]):
        raise ValueError('Feed does not identify immutable channel AppImage')
    return plan


def freshness(repo, plan):
    if remote_sha(repo, 'refs/heads/patch-queue') != plan['expectedAutomation']:
        raise ValueError('Patch queue changed while testing')
    upstream = 'https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher.git'
    if plan['channel'] == 'nightly':
        selected = git(repo, 'ls-remote', upstream, 'refs/heads/main').split()[0]
    else:
        release = json.loads(command(['gh', 'api', 'repos/Heroic-Games-Launcher/HeroicGamesLauncher/releases/latest']))
        if release['tag_name'] != plan['upstream']['tag']:
            raise ValueError('Latest upstream release changed')
        rows = git(repo, 'ls-remote', upstream, 'refs/tags/' + release['tag_name'], 'refs/tags/' + release['tag_name'] + '^{}').splitlines()
        refs = dict(row.split()[::-1] for row in rows)
        selected = refs.get('refs/tags/' + release['tag_name'] + '^{}', refs.get('refs/tags/' + release['tag_name']))
    if selected != plan['base']:
        raise ValueError('Upstream changed while testing')


def publish_release(output, plan):
    output = Path(output)
    result = subprocess.run(['gh', 'release', 'view', plan['tag'], '--repo', REPOSITORY, '--json', 'databaseId'],
                            capture_output=True, text=True)
    files = [str(p) for p in sorted(output.iterdir())]
    nightly = plan.get('channel') == 'nightly'
    if result.returncode:
        if 'HTTP 404' not in result.stderr and 'release not found' not in result.stderr.lower():
            raise RuntimeError('Cannot inspect existing release: ' + result.stderr)
        command(['gh', 'release', 'create', plan['tag'], *files, '--repo', REPOSITORY,
                 '--verify-tag', '--draft', '--latest=false',
                 *(['--prerelease'] if nightly else []),
                 '--title', 'Heroic ' + plan['tag'] + ' — unofficial downstream',
                 '--notes-file', str(output / 'RELEASE-NOTES.md')])
    else:
        release_id = json.loads(result.stdout)['databaseId']
        release = json.loads(command(['gh', 'api', f'repos/{REPOSITORY}/releases/{release_id}']))
        assets = {p['name']: p for p in release['assets']}
        if set(assets) - {Path(p).name for p in files}:
            raise ValueError('Existing release contains unexpected assets')
        for filename in files:
            path = Path(filename)
            if path.name in assets:
                with path.open('rb') as stream:
                    digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
                if assets[path.name].get('digest') != digest:
                    raise ValueError('Refusing to overwrite mismatched release bytes: ' + path.name)
            elif not release['draft']:
                raise ValueError('Published release is immutable')
            else:
                command(['gh', 'release', 'upload', plan['tag'], filename, '--repo', REPOSITORY])
    # Check every uploaded byte before exposing a draft or advancing any feed.
    release_id = json.loads(command(['gh', 'release', 'view', plan['tag'], '--repo', REPOSITORY, '--json', 'databaseId']))['databaseId']
    release = json.loads(command(['gh', 'api', f'repos/{REPOSITORY}/releases/{release_id}']))
    assets = {p['name']: p for p in release['assets']}
    for filename in files:
        with Path(filename).open('rb') as stream:
            digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
        if assets.get(Path(filename).name, {}).get('digest') != digest:
            raise ValueError('Uploaded release hash mismatch')
    freshness('.', plan)
    command(['gh', 'release', 'edit', plan['tag'], '--repo', REPOSITORY, '--draft=false',
             '--prerelease=true' if nightly else '--prerelease=false',
             '--latest=false' if nightly else '--latest'])


def publish(repo, output, channel, build_id, patch_queue_sha):
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('Publication restricted to fork')
    plan = verify(repo, output, channel, build_id, patch_queue_sha, signed=channel == 'stable')
    freshness(repo, plan)
    tag_ref = 'refs/tags/' + plan['tag']
    existing_tag = remote_sha(repo, tag_ref, required=False)
    if existing_tag and existing_tag != plan['candidate']:
        raise ValueError('Published identity reserved for another source')
    pushes = [f"{plan['candidate']}:{tag_ref}"]
    leases = [f'--force-with-lease={tag_ref}:{existing_tag}']
    if channel == 'nightly':
        expected = plan['expectedMain']
        if remote_sha(repo, 'refs/heads/main', required=False) != expected:
            raise ValueError('main advanced while testing')
        backup = 'refs/tags/downstream-backup/' + build_id
        leases += [f'--force-with-lease=refs/heads/main:{expected}', f'--force-with-lease={backup}:']
        pushes += [f"{plan['candidate']}:refs/heads/main"]
        if expected:
            git(repo, 'fetch', '--no-tags', 'origin', expected)
            pushes += [f'{expected}:{backup}']
    git(repo, 'push', '--atomic', *leases, 'origin', *pushes)
    output = Path(output)
    (output / 'source.bundle').unlink()
    (output / 'RELEASE-NOTES.md').write_text(render_notes(plan))
    checksums(output)
    if channel == 'stable':
        command(['bash', '.github/downstream/publish.sh', str(output)])
    else:
        publish_release(output, plan)


def sync_main(repo, output, expected_main):
    plan = json.loads((Path(output) / "build-info.json").read_text())
    if plan.get("channel") != "nightly" or not SHA.fullmatch(expected_main):
        raise ValueError("Only nightly candidates may update generated main")
    checksums(output, verify=True)
    if remote_sha(repo, "refs/heads/main") != expected_main:
        raise ValueError("main advanced while testing")
    git(repo, "push", f"--force-with-lease=refs/heads/main:{expected_main}", "origin", f"{plan['candidate']}:refs/heads/main")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "sync-main", "publish")); parser.add_argument("--repo", default=".")
    parser.add_argument('--patch-queue-sha')
    parser.add_argument('--skip-published', action='store_true')
    parser.add_argument("--source"); parser.add_argument("--output", required=True); parser.add_argument("--upstream-sha")
    parser.add_argument("--upstream-tag"); parser.add_argument("--channel"); parser.add_argument("--build-id"); parser.add_argument("--expected-main")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.repo, args.source, args.output, args.upstream_sha, args.upstream_tag, args.channel, args.build_id, args.skip_published)
    elif args.operation == 'publish':
        publish(args.repo, args.output, args.channel, args.build_id, args.patch_queue_sha)
    else:
        sync_main(args.repo, args.output, args.expected_main)
