"""Maintain Heroic's linear downstream patch series using only Git and the stdlib."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = "felixfoertsch/HeroicGamesLauncher"
UPSTREAM = "Heroic-Games-Launcher/HeroicGamesLauncher"
SHA = re.compile(r"[0-9a-f]{40}")


def command(argv, *, cwd=None, data=None):
    result = subprocess.run(argv, cwd=cwd, input=data, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode:
        raise RuntimeError(f"{argv[0]} failed ({result.returncode}):\n{result.stderr}")
    return result.stdout.strip()


def git(repo, *args, data=None):
    return command(["git", "-C", str(repo), "-c", "user.name=Heroic downstream",
                    "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                    *args], data=data)


def ancestor(repo, older, newer):
    result = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                             older, newer], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def remote_sha(repo, name, required=True):
    value = git(repo, "ls-remote", "--refs", "origin", name)
    if not value and not required:
        return ""
    lines = value.splitlines()
    if len(lines) != 1 or lines[0].split()[1] != name:
        raise ValueError(f"Cannot resolve required remote ref: {name}")
    sha = lines[0].split()[0]
    if not SHA.fullmatch(sha):
        raise ValueError("Expected a full commit SHA")
    return sha


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def outputs(values):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in values.items():
                value = str(value).lower() if isinstance(value, bool) else str(value)
                if "\n" in value or "\r" in value:
                    raise ValueError("Multiline action output rejected")
                output.write(f"{key}={value}\n")


def stable_tag(release):
    tag = release.get("tag_name", "")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Only published stable upstream releases are accepted")
    if not isinstance(tag, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+", tag):
        raise ValueError("Unrecognized stable release tag; manual review required")
    return tag


def patch_series(repo, base, head):
    if not ancestor(repo, base, head):
        raise ValueError("downstream-base must be an ancestor of main")
    if git(repo, "rev-list", "--merges", f"{base}..{head}"):
        raise ValueError("Local patch series contains merges; keep it linear")
    return git(repo, "rev-list", "--reverse", f"{base}..{head}").splitlines()


def replay(repo, source, base, head, new_base):
    """Replay without mutating any existing branch; never silently discard a patch."""
    patches = patch_series(repo, base, head)
    if not ancestor(repo, base, new_base):
        raise ValueError("Refusing a rewind or unrelated upstream history")
    if Path(source).exists():
        raise ValueError("Source destination already exists")
    git(repo, "worktree", "add", "--detach", str(source), new_base)
    results = []
    for sha in patches:
        subject = git(repo, "show", "-s", "--format=%s", sha)
        # Only Git's exact ancestry/patch-equivalence evidence permits an automatic skip.
        equivalent = ancestor(repo, sha, new_base) or git(
            repo, "cherry", new_base, sha, f"{sha}^"
        ).startswith("- ")
        if equivalent:
            # Historical equivalence alone is insufficient: upstream may have reverted it.
            # Require the patch's effect to be present in the current candidate as well.
            diff = git(repo, "show", "--format=", "--binary", sha)
            try:
                if diff:
                    git(source, "apply", "--reverse", "--check", data=diff + "\n")
                results.append({"original": sha, "subject": subject, "status": "upstream-equivalent"})
                continue
            except RuntimeError:
                pass  # Reapply a reverted patch, or stop for review if it no longer applies.
        try:
            git(source, "cherry-pick", "--no-gpg-sign", "--empty=stop", sha)
        except RuntimeError as error:
            paths = git(source, "diff", "--name-only", "--diff-filter=U")
            raise RuntimeError(f"Patch {sha} ({subject}) needs manual review.\n"
                               f"Conflicting paths: {paths or 'none; possibly an empty patch'}\n"
                               "No main/base ref was changed.\n" + str(error)) from error
        results.append({"original": sha, "subject": subject, "status": "replayed",
                        "commit": git(source, "rev-parse", "HEAD")})
    return git(source, "rev-parse", "HEAD"), results


def prepare(repo, source, output, release, build_id, event):
    repo, source, output = Path(repo).resolve(), Path(source).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[1-9]\d*\.[1-9]\d*", build_id):
        raise ValueError("Build ID must be run-id.run-attempt")
    if source.exists() or output.exists():
        raise ValueError("Source/output destination already exists")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Control checkout contains uncommitted changes")
    head = git(repo, "rev-parse", "HEAD")
    base = remote_sha(repo, "refs/heads/downstream-base")
    published = remote_sha(repo, "refs/heads/downstream-published", required=False)
    git(repo, "fetch", "--no-tags", "origin", base)
    patches = patch_series(repo, base, head)
    tag = stable_tag(release)
    incoming = f"refs/downstream-incoming/{tag}"
    git(repo, "fetch", "--no-tags", f"https://github.com/{UPSTREAM}.git",
        f"+refs/tags/{tag}:{incoming}")
    upstream_sha = git(repo, "rev-parse", f"{incoming}^{{commit}}")
    # The initial tested baseline is newer than v2.22.1. Never downgrade it.
    if ancestor(repo, upstream_sha, base):
        new_base = base
    elif ancestor(repo, base, upstream_sha):
        new_base = upstream_sha
    else:
        raise ValueError("Latest stable tag diverges from the recorded baseline; review required")
    should_build = event != "schedule" or new_base != base or published != head
    output.mkdir(parents=True)
    if new_base != base:
        candidate, replayed = replay(repo, source, base, head, new_base)
    else:
        candidate = head
        replayed = [{"original": sha, "commit": sha, "status": "retained",
                     "subject": git(repo, "show", "-s", "--format=%s", sha)} for sha in patches]
        if should_build:
            git(repo, "worktree", "add", "--detach", str(source), head)
    pkg = json.loads(git(repo, "show", f"{candidate}:package.json"))
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:[-+].*)?", pkg["version"])
    if not match:
        raise ValueError("Unrecognized application version")
    version = f"{match[1]}-felix.{build_id}"
    plan = {"schema": 1, "repository": REPOSITORY, "expectedMain": head,
            "expectedBase": base, "expectedPublished": published,
            "candidate": candidate, "base": new_base, "build": should_build,
            "upstream": {"tag": tag, "sha": upstream_sha}, "patches": replayed,
            "version": version, "tag": f"v{version}", "buildId": build_id,
            "packageManager": pkg.get("packageManager"),
            "pacmanVersion": f"{match[1]}.felix{build_id.split('.')[0]}",
            "pacmanRelease": build_id.split('.')[1]}
    write_json(output / "build-info.json", plan)
    if should_build:
        git(repo, "update-ref", "refs/downstream-candidate", candidate)
        git(repo, "bundle", "create", str(output / "source.bundle"),
            "refs/downstream-candidate", f"^{base}")
        git(repo, "archive", "--format=tar.gz", f"--prefix=Heroic-{version}/",
            f"--output={output / ('Heroic-' + version + '-source.tar.gz')}", candidate)
    outputs({"build": should_build, "candidate": candidate, "version": version,
             "tag": plan["tag"], "pacman_version": plan["pacmanVersion"],
             "pacman_release": plan["pacmanRelease"]})
    summary = (f"## Downstream check\n\nUpstream: `{tag}` (`{upstream_sha}`).\n\n"
               f"Baseline: `{new_base}`. Source: `{candidate}`. Build required: {should_build}.\n\n" +
               "\n".join(f"- {p['status']}: `{p['original']}` {p['subject']}" for p in replayed) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(summary)
    print(summary)
    return plan


def packaging(source, output):
    output = Path(output)
    plan = json.loads((output / "build-info.json").read_text())
    config = {"extends": str(Path(source).resolve() / "electron-builder.yml"),
              "extraMetadata": {"version": plan["version"],
                                "repository": {"type": "git", "url": f"https://github.com/{REPOSITORY}"}},
              "publish": [{"provider": "github", "owner": "felixfoertsch",
                           "repo": "HeroicGamesLauncher", "releaseType": "release"}],
              "linux": {"artifactName": "Heroic-${version}-custom-${arch}.${ext}"}}
    write_json(output / "packaging.json", config)
    notes = (f"# Heroic {plan['version']}\n\nUnofficial Linux x64 downstream build.\n\n"
             f"Source: `{plan['candidate']}`. Upstream baseline: `{plan['base']}`.\n"
             f"Latest stable release checked: `{plan['upstream']['tag']}`.\n\n"
             "## Carried changes\n\n" +
             "\n".join(f"- {p['status']}: {p['subject']} (`{p.get('commit', p['original'])}`)"
                       for p in plan['patches']) + "\n\n"
             "Includes exact source and generated build-info.json; no feature manifest is maintained.\n"
             "See doc/downstream.md for updates, signing, recovery and independent contributions.\n"
             "AI-assisted implementation by Astra (OpenAI), directed by Felix. Earlier feature smoke tests were reported by Felix; this build has automated checks only.\n")
    (output / "RELEASE-NOTES.md").write_text(notes)


def checksums(output, verify=False):
    output = Path(output)
    if verify:
        verified = set()
        for line in (output / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            if Path(name).name != name or not re.fullmatch(r"[a-zA-Z0-9_.+-]+", name):
                raise ValueError("Unsafe artifact filename")
            path = output / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Artifact is not a regular file")
            if name in verified:
                raise ValueError("Duplicate checksum entry")
            verified.add(name)
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        actual_files = {p.name for p in output.iterdir() if p.name != "SHA256SUMS"}
        if actual_files != verified:
            raise ValueError("Artifact set differs from the checksum list")
        return
    lines = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            if path.is_symlink():
                raise ValueError("Symlink artifact rejected")
            with path.open("rb") as stream:
                lines.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}\n")
    (output / "SHA256SUMS").write_text("".join(lines))


def promote(repo, output, expected_head):
    """Atomically promote tested source+baseline, guarded against concurrent edits."""
    output = Path(output).resolve()
    checksums(output, verify=True)
    plan = json.loads((output / "build-info.json").read_text())
    if plan["repository"] != REPOSITORY or plan["expectedMain"] != expected_head:
        raise ValueError("Unexpected source repository or initial main commit")
    for key in ("candidate", "base", "expectedMain", "expectedBase"):
        if not SHA.fullmatch(plan[key]):
            raise ValueError("Invalid promotion SHA")
    if not re.fullmatch(r"v\d+\.\d+\.\d+-felix\.\d+\.\d+", plan["tag"]):
        raise ValueError("Invalid release tag")
    git(repo, "bundle", "verify", str(output / "source.bundle"))
    git(repo, "fetch", str(output / "source.bundle"),
        "refs/downstream-candidate:refs/downstream-promote")
    if git(repo, "rev-parse", "refs/downstream-promote") != plan["candidate"]:
        raise ValueError("Bundle does not contain the tested source")
    patch_series(repo, plan["base"], plan["candidate"])
    if remote_sha(repo, "refs/heads/main") != plan["expectedMain"]:
        raise ValueError("main advanced while testing; refusing to overwrite it")
    if remote_sha(repo, "refs/heads/downstream-base") != plan["expectedBase"]:
        raise ValueError("downstream-base advanced while testing")
    tag_ref = f"refs/tags/{plan['tag']}"
    backup = f"refs/tags/downstream-backup/{plan['buildId']}"
    git(repo, "push", "--atomic",
        f"--force-with-lease=refs/heads/main:{plan['expectedMain']}",
        f"--force-with-lease=refs/heads/downstream-base:{plan['expectedBase']}",
        f"--force-with-lease={tag_ref}:", f"--force-with-lease={backup}:", "origin",
        f"{plan['candidate']}:refs/heads/main", f"{plan['base']}:refs/heads/downstream-base",
        f"{plan['candidate']}:{tag_ref}", f"{plan['expectedMain']}:{backup}")
    return plan


def finish(repo, output):
    plan = json.loads((Path(output) / "build-info.json").read_text())
    # Publication failures leave this marker unchanged, so the next check retries.
    git(repo, "push", f"--force-with-lease=refs/heads/downstream-published:{plan['expectedPublished']}",
        "origin", f"{plan['candidate']}:refs/heads/downstream-published")



def record_status(repo):
    """Daily metadata-only heartbeat, plus immediate changes of state/source."""
    now = datetime.now(timezone.utc).isoformat()
    state = "failure" if os.environ.get("BUILD_RESULT") == "failure" or os.environ.get("PUBLISH_RESULT") == "failure" else "success"
    run_url = f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    payload = {"checkedAt": now, "result": state, "source": os.environ["GITHUB_SHA"],
               "candidate": os.environ.get("CANDIDATE", ""), "run": run_url,
               "build": os.environ.get("BUILD_RESULT"), "publish": os.environ.get("PUBLISH_RESULT")}
    ref = "refs/heads/downstream-status"
    previous = remote_sha(repo, ref, required=False)
    old = {}
    if previous:
        git(repo, "fetch", "--no-tags", "origin", previous)
        old = json.loads(git(repo, "show", f"{previous}:last-check.json"))
    if not (old.get("checkedAt", "")[:10] == now[:10] and old.get("result") == state
            and old.get("source") == payload["source"] and old.get("publish") == payload["publish"]):
        blob = git(repo, "hash-object", "-w", "--stdin", data=json.dumps(payload, indent=2) + "\n")
        tree = git(repo, "mktree", data=f"100644 blob {blob}\tlast-check.json\n")
        parents = ["-p", previous] if previous else []
        commit = git(repo, "commit-tree", tree, *parents, data="ci: record downstream health\n")
        git(repo, "push", f"--force-with-lease={ref}:{previous}", "origin", f"{commit}:{ref}")
    title = "Downstream build needs attention"
    marker = "<!-- heroic-downstream-status -->"
    try:
        issues = json.loads(command(["gh", "issue", "list", "--repo", REPOSITORY,
                                     "--state", "open", "--search", f'"{title}" in:title',
                                     "--json", "number,title,body"]))
        issue = next((i for i in issues if i["title"] == title and marker in i["body"]), None)
        if state == "failure":
            body = f"{marker}\nThe downstream update/build is blocked.\n\nRun: {run_url}\n\nThe previous published release remains available. Inspect the failed job before retrying. No patch is silently dropped."
            if issue:
                command(["gh", "issue", "edit", str(issue["number"]), "--repo", REPOSITORY, "--body", body])
            else:
                command(["gh", "issue", "create", "--repo", REPOSITORY, "--title", title,
                         "--body", body, "--assignee", "felixfoertsch"])
        elif issue and os.environ.get("PUBLISH_RESULT") == "success":
            command(["gh", "issue", "close", str(issue["number"]), "--repo", REPOSITORY,
                     "--comment", f"Recovered: {run_url}"])
    except RuntimeError as error:
        print(f"Issue reporting unavailable; consult the Actions run: {error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "packaging", "checksums", "verify", "promote", "finish", "status"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source")
    parser.add_argument("--output", required=True)
    parser.add_argument("--release")
    parser.add_argument("--build-id")
    parser.add_argument("--event", default="workflow_dispatch")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.repo, args.source, args.output, json.loads(Path(args.release).read_text()),
                args.build_id, args.event)
    elif args.operation == "packaging":
        packaging(args.source, args.output)
    elif args.operation == "checksums":
        checksums(args.output)
    elif args.operation == "verify":
        checksums(args.output, verify=True)
    elif args.operation == "promote":
        promote(args.repo, args.output, args.expected_head)
    elif args.operation == "finish":
        finish(args.repo, args.output)
    else:
        record_status(args.repo)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
