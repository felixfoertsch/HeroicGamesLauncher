"""Build exact branch revisions and publish isolated, immutable test prereleases."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

from calver import CORE, REPOSITORY
from downstream import command, git, outputs, patch_series, remote_sha, write_json, checksums, SHA
from release_notes import DISCLOSURE

CI_MARKER = "Downstream-CI: true"
INTERNAL_BRANCHES = {"main", "downstream-base", "downstream-published", "downstream-status", "upstream-base"}


def identity(branch, sha, build_id, core):
    if not isinstance(branch, str) or branch in INTERNAL_BRANCHES:
        raise ValueError("Expected a development branch, not a main/metadata ref")
    command(["git", "check-ref-format", f"refs/heads/{branch}"])
    if not SHA.fullmatch(sha) or not re.fullmatch(r"[1-9]\d*\.[1-9]\d*", build_id):
        raise ValueError("Expected an exact SHA and run-id.run-attempt")
    if not re.fullmatch(CORE, core):
        raise ValueError("Expected an ordinary upstream application version")
    slug = re.sub(r"[^a-z0-9-]+", "-", branch.lower()).strip("-")[:40] or "branch"
    key = slug + "-" + hashlib.sha256(branch.encode()).hexdigest()[:12]
    tag = f"preview-{key}-{build_id}-{sha[:12]}"
    return {"branchKey": key, "tag": tag, "version": f"{core}-branch.{key}.{build_id}",
            "pacmanVersion": f"{core}_branch.{key.replace(chr(45), chr(95))}.{build_id}", "pacmanRelease": "1",
            "artifactName": f"branch-{key}-{build_id}-{sha[:12]}",
            "feedUrl": f"https://github.com/{REPOSITORY}/releases/download/{tag}"}


def describe(repo, head):
    """The CI commit's parent pins this branch's upstream, even after main advances."""
    matches = git(repo, "log", "--first-parent", "--format=%H", "--fixed-strings",
                  f"--grep={CI_MARKER}", head).splitlines()
    anchors = [sha for sha in matches if CI_MARKER in git(repo, "show", "-s", "--format=%B", sha).splitlines()]
    if len(anchors) != 1:
        raise ValueError("Branch must contain exactly one CI-first infrastructure commit")
    ci = anchors[0]
    parents = git(repo, "show", "-s", "--format=%P", ci).split()
    if len(parents) != 1:
        raise ValueError("The CI commit must have one upstream parent")
    base = parents[0]
    commits = patch_series(repo, base, head)
    if not commits or commits[0] != ci:
        raise ValueError("The first downstream commit must be CI")
    core = json.loads(git(repo, "show", f"{base}:package.json"))["version"]
    if not re.fullmatch(CORE, core):
        raise ValueError("Branch baseline must be a stable upstream version")
    patches = [{"commit": sha, "subject": git(repo, "show", "-s", "--format=%s", sha)} for sha in commits]
    return {"base": base, "ci": ci, "upstream": {"tag": f"v{core}", "sha": base}, "patches": patches}


def plan_for(repo, branch, sha, build_id):
    description = describe(repo, sha)
    core = description["upstream"]["tag"].removeprefix("v")
    return {"schema": 1, "kind": "branch", "repository": REPOSITORY, "branch": branch,
            "candidate": sha, "buildId": build_id, "build": True, **description,
            **identity(branch, sha, build_id, core)}


def notes(plan):
    branch = plan["branch"].replace("`", "'")
    commits = "\n".join(
        f"- `{p['subject'].replace('`', chr(39))}` ([`{p['commit'][:8]}`]"
        f"(https://github.com/{REPOSITORY}/commit/{p['commit']}))" for p in plan["patches"])
    return (f"{DISCLOSURE}\n\n## Branch preview: `{branch}`\n\n"
            "Unofficial **Linux x86-64 test build**, not a main release.\n\n"
            f"Exact pushed revision: `{plan['candidate']}`. Run/attempt: `{plan['buildId']}`.\n"
            f"Upstream: `{plan['upstream']['tag']}` (`{plan['base']}`).\n\n"
            "### Commits on top of upstream\n\n" + commits + "\n\n"
            "### Testing and updates\n\n"
            "AppImage, tar.xz, an unsigned local-test Arch package, exact source, build provenance "
            "and SHA256 checksums are attached. Back up your Heroic configuration before testing; "
            "these packages use the normal Heroic profile. The Arch package is for deliberate "
            "local testing, not a signed pacman update repository.\n\n"
            "This immutable prerelease never replaces Latest, main's CalVer releases, "
            "downstream-feed or the signed pacman repository. Its AppImage feed is pinned to "
            "this exact preview; install another branch build manually to change revisions.\n\n"
            "Publication requires TypeScript, Jest, ESLint, Prettier, Linux packaging and a "
            "disposable-key pacman test. These automated checks do not establish that live "
            "Amazon authentication, MFA or interactive game actions are correct.\n")


def prepare(repo, source, output, branch, build_id):
    repo, source, output = (Path(p).resolve() for p in (repo, source, output))
    if source.exists() or output.exists():
        raise ValueError("Source/output destination already exists")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Control checkout contains uncommitted changes")
    head = git(repo, "rev-parse", "HEAD")
    plan = plan_for(repo, branch, head, build_id)
    output.mkdir(parents=True)
    git(repo, "worktree", "add", "--detach", str(source), head)
    write_json(output / "build-info.json", plan)
    git(repo, "archive", "--format=tar.gz", f"--prefix=Heroic-{plan['tag']}/",
        f"--output={output / ('Heroic-' + plan['tag'] + '-source.tar.gz')}", head)
    (output / "RELEASE-NOTES.md").write_text(notes(plan))
    (output / "SIGNING-STATUS.txt").write_text("Unsigned branch test package. Not published to the signed pacman channel.\n")
    outputs({"build": True, "candidate": head, "artifact_name": plan["artifactName"],
             "pacman_version": plan["pacmanVersion"], "pacman_release": plan["pacmanRelease"]})
    return plan


def packaging(source, output):
    output = Path(output)
    plan = json.loads((output / "build-info.json").read_text())
    validate_identity(plan)
    write_json(output / "packaging.json", {
        "extends": str(Path(source).resolve() / "electron-builder.yml"),
        "extraMetadata": {"version": plan["version"], "repository": {
            "type": "git", "url": f"https://github.com/{REPOSITORY}"}},
        "detectUpdateChannel": False,
        "publish": [{"provider": "generic", "url": plan["feedUrl"], "channel": "latest"}],
        "linux": {"artifactName": "Heroic-" + plan["tag"] + "-custom-${arch}.${ext}"}})


def validate_identity(plan):
    if plan.get("schema") != 1 or plan.get("kind") != "branch" or plan.get("repository") != REPOSITORY:
        raise ValueError("Unexpected branch build provenance")
    expected = identity(plan["branch"], plan["candidate"], plan["buildId"], plan["upstream"]["tag"].removeprefix("v"))
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValueError(f"Branch build identity mismatch: {key}")


def write_feed(output):
    output = Path(output)
    plan = json.loads((output / "build-info.json").read_text())
    validate_identity(plan)
    images = list(output.glob(f"Heroic-{plan['tag']}-custom-*.AppImage"))
    if len(images) != 1 or images[0].is_symlink() or not images[0].is_file():
        raise ValueError("Expected one branch AppImage")
    image = images[0]
    with image.open("rb") as stream:
        digest = base64.b64encode(hashlib.file_digest(stream, "sha512").digest()).decode("ascii")
    url = plan["feedUrl"] + "/" + quote(image.name)
    write_json(output / "latest-linux.yml", {"version": plan["version"],
               "files": [{"url": url, "sha512": digest, "size": image.stat().st_size}],
               "path": url, "sha512": digest, "releaseName": plan["tag"],
               "releaseDate": datetime.now(timezone.utc).isoformat()})


def verify(repo, output, branch, sha, build_id):
    output = Path(output)
    checksums(output, verify=True)
    plan = json.loads((output / "build-info.json").read_text())
    validate_identity(plan)
    if plan != plan_for(repo, branch, sha, build_id):
        raise ValueError("Artifact provenance differs from the exact triggering revision")
    required = {"build-info.json", "RELEASE-NOTES.md", "packaging.json", "latest-linux.yml",
                "SIGNING-STATUS.txt", "archlinux-image.txt", "SHA256SUMS",
                f"Heroic-{plan['tag']}-source.tar.gz"}
    for pattern in (f"Heroic-{plan['tag']}-custom-*.AppImage", f"Heroic-{plan['tag']}-custom-*.tar.xz",
                    f"heroic-felix-{plan['pacmanVersion']}-{plan['pacmanRelease']}-x86_64.pkg.tar.zst"):
        matches = list(output.glob(pattern))
        if len(matches) != 1:
            raise ValueError("Incomplete or ambiguous branch packages")
        required.add(matches[0].name)
    if required != {p.name for p in output.iterdir()}:
        raise ValueError("Unexpected or incomplete branch artifact set")
    feed = json.loads((output / "latest-linux.yml").read_text())
    if feed.get("version") != plan["version"] or feed.get("releaseName") != plan["tag"]:
        raise ValueError("Incorrect preview update version")
    image = next(output.glob(f"Heroic-{plan['tag']}-custom-*.AppImage"))
    expected_url = plan["feedUrl"] + "/" + quote(image.name)
    with image.open("rb") as stream:
        digest = base64.b64encode(hashlib.file_digest(stream, "sha512").digest()).decode("ascii")
    expected_files = [{"url": expected_url, "sha512": digest, "size": image.stat().st_size}]
    if feed.get("path") != expected_url or feed.get("sha512") != digest or feed.get("files") != expected_files:
        raise ValueError("Preview feed must identify only its own immutable AppImage")
    return plan


def publish(repo, output, branch, sha, build_id):
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("Publication is restricted to Felix's fork")
    if not SHA.fullmatch(sha):
        raise ValueError("Invalid expected source SHA")
    # Import objects only. Never check out or execute a branch's code with write access.
    git(repo, "fetch", "--no-tags", "origin", sha)
    output = Path(output).resolve()
    plan = verify(repo, output, branch, sha, build_id)
    if remote_sha(repo, f"refs/tags/{plan['tag']}", required=False):
        raise ValueError("Preview tag already exists; rerun the whole workflow for a new attempt")
    (output / "RELEASE-NOTES.md").write_text(notes(plan))
    checksums(output)
    files = [str(path) for path in sorted(output.iterdir())]
    command(["gh", "release", "create", plan["tag"], *files, "--repo", REPOSITORY,
             "--target", sha, "--draft", "--prerelease", "--latest=false",
             "--title", f"Preview: {branch} ({sha[:8]})", "--notes-file", str(output / "RELEASE-NOTES.md")])
    command(["gh", "release", "edit", plan["tag"], "--repo", REPOSITORY,
             "--draft=false", "--prerelease", "--latest=false"])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(f"[Branch preview](https://github.com/{REPOSITORY}/releases/tag/{plan['tag']})\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "packaging", "feed", "publish"])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source")
    parser.add_argument("--output", required=True)
    parser.add_argument("--branch")
    parser.add_argument("--sha")
    parser.add_argument("--build-id")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.repo, args.source, args.output, args.branch, args.build_id)
    elif args.operation == "packaging":
        packaging(args.source, args.output)
    elif args.operation == "feed":
        write_feed(args.output)
    else:
        publish(args.repo, args.output, args.branch, args.sha, args.build_id)
