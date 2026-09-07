"""Render disclosure-first downstream release notes from validated build provenance."""
import argparse
import json
from pathlib import Path
import re

from calver import REPOSITORY, validate_plan_version

DISCLOSURE = (
    "**AI disclosure:** I am **Astra, an OpenAI AI assistant**. I prepared the "
    "downstream changes, automation and this description at **Felix Förtsch's** "
    "direction. Upstream Heroic remains the work of its contributors."
)
DOCS = f"https://github.com/{REPOSITORY}/blob/main/doc/downstream.md"
SHA = re.compile(r"[0-9a-f]{40}")


def render_notes(plan, signed=False):
    validate_plan_version(plan)
    if plan.get("repository") != REPOSITORY:
        raise ValueError("Unexpected downstream repository")
    for key in ("candidate", "base"):
        if not SHA.fullmatch(plan.get(key, "")):
            raise ValueError(f"Invalid source identity: {key}")
    patches = []
    upstream_equivalent = []
    for patch in plan.get("patches", []):
        sha = patch.get("commit", patch.get("original", ""))
        status = patch.get("status")
        subject = patch.get("subject")
        if not SHA.fullmatch(sha) or status not in ("replayed", "retained", "upstream-equivalent"):
            raise ValueError("Invalid patch provenance")
        if not isinstance(subject, str) or any(c in subject for c in "\r\n"):
            raise ValueError("Patch subject must be a single line")
        # Commit subjects are displayed as text, never interpreted as shell input.
        label = subject.replace("`", "'")
        destination = upstream_equivalent if status == "upstream-equivalent" else patches
        destination.append(f"- {status}: `{label}` ([`{sha[:8]}`](https://github.com/{REPOSITORY}/commit/{sha}))")
    distribution = (
        "The signed `heroic-felix` Arch package and repository databases are included. "
        "Verify and trust the dedicated public key before adding the pacman source."
        if signed else
        "Production package signing is not configured for this release. AppImage and "
        "tar.xz are available; no unsigned pacman update repository is published."
    )
    tag = plan["tag"]
    return (
        f"{DISCLOSURE}\n\n"
        f"## Heroic {tag}\n\n"
        f"Unofficial **Linux x86-64** build of upstream **{plan['upstream']['tag']}** "
        "with this fork's linear patch series. Upstream PR decisions do not remove our local fixes.\n\n"
        "### Version\n\n"
        f"Public tag and filenames: **`{tag}`**. The format is "
        "`heroic-release-tag-YYYY.MM.DD.n`; the date uses Europe/Berlin and `n` starts "
        "at 1 for each upstream-tag/date pair. Reserved tags are never reused.\n\n"
        f"Electron's internal version is `{plan['version']}`; Arch's package version is "
        f"`{plan['pacmanVersion']}-{plan['pacmanRelease']}`. These compatible encodings "
        "preserve numeric update ordering; the public release keeps the padded CalVer spelling.\n\n"
        "### Commits on top of upstream\n\n"
        f"Exact downstream range: [`{plan['base'][:8]}..{plan['candidate'][:8]}`]"
        f"(https://github.com/{REPOSITORY}/compare/{plan['base']}...{plan['candidate']}). "
        "Listed oldest first, beginning with CI; only integrated features/fixes follow.\n\n" +
        ("\n".join(patches) or "No downstream commits.") + "\n\n" +
        (("### Already supplied by upstream\n\n" + "\n".join(upstream_equivalent) + "\n\n")
         if upstream_equivalent else "") +
        "### Installation and updates\n\n"
        f"{distribution}\n\n"
        "For migration from the old `-felix.<run-id>.<attempt>` builds, install the first "
        "CalVer AppImage manually once. Subsequent AppImage updates use this fork's "
        "`downstream-feed`; native Arch installations update through pacman once signing is set up. "
        "Back up Heroic's configuration before switching packages.\n\n"
        f"[Setup, signing and recovery instructions]({DOCS}).\n\n"
        "### Source and validation\n\n"
        f"Built source: [`{plan['candidate']}`](https://github.com/{REPOSITORY}/commit/{plan['candidate']}).\n"
        f"Upstream baseline: `{plan['base']}`. Exact source, generated `build-info.json` "
        "and SHA256 checksums accompany the binaries. There is no maintained feature-selection manifest.\n\n"
        "Publication follows TypeScript, Jest, ESLint, Prettier, Linux packaging and a "
        "disposable-key pacman signature/download test. These checks do not substitute "
        "for interactive testing or live Amazon/MFA testing of this particular release. "
        "No fresh desktop smoke test or live-account test is claimed for this release.\n"
    )


def channel_notes(channel):
    if channel == "downstream-feed":
        description = (
            "Mutable AppImage update metadata pointing to a fully published, versioned "
            "CalVer release. This is an update channel, **not an application version**."
        )
    elif channel == "pacman":
        description = (
            "Rolling signed pacman package index for `heroic-felix`. Versioned packages "
            "are retained for clients using an older index. This is an update channel, "
            "**not an application version**. Never disable signature verification."
        )
    else:
        raise ValueError("Unexpected metadata channel")
    return f"{DISCLOSURE}\n\n{description}\n\n[Setup and trust instructions]({DOCS}).\n"


def write_notes(output, signed=False):
    output = Path(output)
    plan = json.loads((output / "build-info.json").read_text())
    (output / "RELEASE-NOTES.md").write_text(render_notes(plan, signed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--signed", action="store_true")
    args = parser.parse_args()
    write_notes(args.output, args.signed)
