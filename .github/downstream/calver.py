"""Public CalVer tags, package-compatible versions, and a generic AppImage feed."""
import base64
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Berlin")
CORE = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
STABLE_TAG = re.compile(rf"v?{CORE}")
RELEASE_TAG = re.compile(rf"(?P<upstream>v?{CORE})-(?P<date>\d{{4}}\.\d{{2}}\.\d{{2}})\.(?P<n>[1-9]\d*)")
REPOSITORY = "felixfoertsch/HeroicGamesLauncher"
FEED_URL = f"https://github.com/{REPOSITORY}/releases/download/downstream-feed"


def release_date(now=None):
    now = now or datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("Release timestamps must include a timezone")
    return now.astimezone(TIMEZONE).strftime("%Y.%m.%d")


def version_fields(upstream_tag, stamp, sequence):
    if not isinstance(upstream_tag, str) or not STABLE_TAG.fullmatch(upstream_tag):
        raise ValueError("CalVer requires an ordinary stable upstream release tag")
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", stamp):
        raise ValueError("Release date must be YYYY.MM.DD")
    year, month, day = map(int, stamp.split("."))
    date(year, month, day)  # Reject impossible calendar dates rather than normalizing them.
    if type(sequence) is not int or not 1 <= sequence <= 9007199254740991:
        raise ValueError("Release sequence must be a positive safe integer")
    core = upstream_tag.removeprefix("v")
    return {
        "tag": f"{upstream_tag}-{stamp}.{sequence}",
        "version": f"{core}-{year}.{month}.{day}.{sequence}",
        "pacmanVersion": f"{core}_{stamp}.{sequence}",
        "pacmanRelease": "1",
        "calver": {"date": stamp, "sequence": sequence, "timezone": "Europe/Berlin"},
    }


def next_version(upstream_tag, existing_tags, now=None):
    stamp = release_date(now)
    used = []
    for tag in existing_tags:
        match = RELEASE_TAG.fullmatch(tag)
        if match and match["upstream"] == upstream_tag and match["date"] == stamp:
            used.append(int(match["n"]))
    return version_fields(upstream_tag, stamp, max(used, default=0) + 1)


def validate_plan_version(plan):
    match = RELEASE_TAG.fullmatch(plan.get("tag", ""))
    if not match:
        raise ValueError("Invalid CalVer release tag")
    expected = version_fields(match["upstream"], match["date"], int(match["n"]))
    if plan.get("upstream", {}).get("tag") != match["upstream"]:
        raise ValueError("CalVer prefix does not identify the selected upstream release")
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValueError(f"CalVer metadata mismatch: {key}")


def write_appimage_feed(output):
    output = Path(output)
    plan = json.loads((output / "build-info.json").read_text())
    validate_plan_version(plan)
    images = list(output.glob(f"Heroic-{plan['tag']}-custom-*.AppImage"))
    if len(images) != 1 or images[0].is_symlink() or not images[0].is_file():
        raise ValueError("Expected one regular AppImage matching this release")
    image = images[0]
    with image.open("rb") as stream:
        digest = base64.b64encode(hashlib.file_digest(stream, "sha512").digest()).decode("ascii")
    url = f"https://github.com/{REPOSITORY}/releases/download/{plan['tag']}/{quote(image.name)}"
    # JSON is a YAML 1.2 subset. GenericProvider reads this metadata, rather than
    # attempting to parse zero-padded public release tags as SemVer.
    metadata = {
        "version": plan["version"],
        "files": [{"url": url, "sha512": digest, "size": image.stat().st_size}],
        "path": url,
        "sha512": digest,
        "releaseName": plan["tag"],
        "releaseDate": datetime.now(TIMEZONE).isoformat(),
    }
    (output / "latest-linux.yml").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Directory containing build-info.json and the built AppImage")
    write_appimage_feed(parser.parse_args().output)
