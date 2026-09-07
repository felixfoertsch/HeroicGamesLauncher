"""Refresh release descriptions and archive legacy run-ID releases after CalVer publication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from calver import CORE, REPOSITORY, RELEASE_TAG, validate_plan_version
from release_notes import DISCLOSURE, channel_notes, render_notes

LEGACY_TAG = re.compile(rf"v?(?P<core>{CORE})-felix\.[1-9]\d*\.[1-9]\d*")


def gh(*args):
    result = subprocess.run(["gh", *args], text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"GitHub operation failed: {result.stderr.strip()}")
    return result.stdout


def legacy_releases(releases, current):
    current_match = RELEASE_TAG.fullmatch(current["tag_name"])
    if not current_match or current.get("draft") or current.get("prerelease"):
        raise ValueError("A published CalVer application release is required")
    current_core = tuple(map(int, current_match["upstream"].removeprefix("v").split(".")))
    candidates = []
    for release in releases:
        match = LEGACY_TAG.fullmatch(release.get("tag_name", ""))
        if not match or release.get("draft"):
            continue
        if tuple(map(int, match["core"].split("."))) > current_core:
            continue
        if not release.get("published_at") or release["published_at"] > current["published_at"]:
            continue
        candidates.append(release)
    return candidates


def verify_replacement(release, plan, feed):
    validate_plan_version(plan)
    if plan.get("repository") != REPOSITORY or release["tag_name"] != plan["tag"]:
        raise ValueError("Unexpected replacement release identity")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Replacement is not a published application release")
    names = {asset["name"] for asset in release.get("assets", []) if asset.get("state") == "uploaded" and asset.get("size", 0) > 0}
    required = {"build-info.json", "SHA256SUMS", "latest-linux.yml", f"Heroic-{plan['tag']}-source.tar.gz"}
    if not required <= names:
        raise ValueError("Replacement release is incomplete")
    images = [name for name in names if name.startswith(f"Heroic-{plan['tag']}-custom-") and name.endswith(".AppImage")]
    if len(images) != 1 or not any(name.startswith(f"Heroic-{plan['tag']}-custom-") and name.endswith(".tar.xz") for name in names):
        raise ValueError("Replacement application packages are missing")
    expected_url = f"https://github.com/{REPOSITORY}/releases/download/{plan['tag']}/{images[0]}"
    if feed.get("version") != plan["version"] or feed.get("releaseName") != plan["tag"] or feed.get("path") != expected_url:
        raise ValueError("AppImage channel has not published this replacement")
    if not any(item.get("url") == expected_url for item in feed.get("files", [])):
        raise ValueError("AppImage file entry disagrees with its release")


def cleanup(apply=False):
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ValueError("Maintenance is restricted to Felix's fork")
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{REPOSITORY}/releases?per_page=100"))
    releases = [release for page in pages for release in page]
    current = json.loads(gh("api", f"repos/{REPOSITORY}/releases/latest"))
    if not RELEASE_TAG.fullmatch(current.get("tag_name", "")):
        print("No published CalVer replacement yet; old releases were preserved.")
        return
    tag = current["tag_name"]
    channels = {r["tag_name"]: r for r in releases if r["tag_name"] in ("downstream-feed", "pacman") and not r.get("draft")}
    if "downstream-feed" not in channels:
        print("CalVer AppImage feed is not published yet; old releases were preserved.")
        return
    with tempfile.TemporaryDirectory(prefix="heroic-release-cleanup-") as directory:
        root = Path(directory)
        gh("release", "download", tag, "--repo", REPOSITORY, "--pattern", "build-info.json", "--pattern", "SHA256SUMS", "--dir", str(root))
        gh("release", "download", "downstream-feed", "--repo", REPOSITORY, "--pattern", "latest-linux.yml", "--dir", str(root))
        entries = [line.split("  ", 1) for line in (root / "SHA256SUMS").read_text().splitlines()]
        matches = [digest for digest, name in entries if name == "build-info.json"]
        if matches != [hashlib.sha256((root / "build-info.json").read_bytes()).hexdigest()]:
            raise ValueError("Replacement build provenance checksum failed")
        plan = json.loads((root / "build-info.json").read_text())
        feed = json.loads((root / "latest-linux.yml").read_text())
        verify_replacement(current, plan, feed)
        names = {asset["name"] for asset in current["assets"]}
        signed = "heroic-felix-key.fingerprint" in names and any(name.endswith(".pkg.tar.zst.sig") for name in names)
        edits = [(tag, f"Heroic {tag} — unofficial downstream", render_notes(plan, signed), False)]
        for channel in channels:
            title = ("AppImage update feed (not an application release)" if channel == "downstream-feed"
                     else "Signed pacman repository (not an application release)")
            edits.append((channel, title, channel_notes(channel), False))
        for old in legacy_releases(releases, current):
            old_tag = old["tag_name"]
            body = (f"{DISCLOSURE}\n\n## Archived run-ID build\n\n"
                    f"Superseded by [{tag}](https://github.com/{REPOSITORY}/releases/tag/{tag}). "
                    "This pre-CalVer release is retained as an owner-visible draft for rollback. "
                    "Its tag and binary assets are unchanged; they have not been renamed to claim a different build version.\n")
            edits.append((old_tag, f"Archived: Heroic {old_tag} (pre-CalVer)", body, True))
        # Refuse to clean up against a release that ceased being latest during verification.
        latest = json.loads(gh("api", f"repos/{REPOSITORY}/releases/latest"))
        if latest.get("id") != current.get("id"):
            raise ValueError("Latest release changed during maintenance; retry")
        for index, (target, title, body, archive) in enumerate(edits):
            print(f"{'Archive' if archive else 'Refresh'} {target}" + ("" if apply else " (dry run)"))
            if not apply:
                continue
            notes = root / f"notes-{index}.md"
            notes.write_text(body)
            arguments = ["release", "edit", target, "--repo", REPOSITORY, "--title", title, "--notes-file", str(notes)]
            if archive:
                arguments += ["--draft=true", "--latest=false"]
            gh(*arguments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply metadata edits; never delete tags or assets")
    cleanup(parser.parse_args().apply)
