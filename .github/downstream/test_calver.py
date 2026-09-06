"""CalVer and updater regression tests; no network or credentials are required."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import calver


class CalVerTests(unittest.TestCase):
    NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)

    def test_public_and_internal_versions(self):
        version = calver.next_version("v2.22.1", [], self.NOW)
        self.assertEqual(version["tag"], "v2.22.1-2026.09.06.1")
        self.assertEqual(version["version"], "2.22.1-2026.9.6.1")
        self.assertEqual(version["pacmanVersion"], "2.22.1_2026.09.06.1")
        self.assertEqual(version["pacmanRelease"], "1")
        self.assertEqual(version["calver"]["timezone"], "Europe/Berlin")

    def test_counter_is_numeric_and_ignores_other_schemes(self):
        tags = ["v2.22.1-2026.09.06.9", "v2.22.1-2026.09.06.10",
                "v2.22.1-felix.999999.1", "v2.22.1-2026.09.06.nope",
                "downstream-feed", "pacman"]
        self.assertEqual(calver.next_version("v2.22.1", tags, self.NOW)["calver"]["sequence"], 11)

    def test_sequence_resets_for_a_new_day_or_upstream_release(self):
        tags = ["v2.22.1-2026.09.06.100"]
        tomorrow = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
        self.assertEqual(calver.next_version("v2.22.1", tags, tomorrow)["tag"], "v2.22.1-2026.09.07.1")
        self.assertEqual(calver.next_version("v2.22.2", tags, self.NOW)["tag"], "v2.22.2-2026.09.06.1")

    def test_preserves_an_upstream_tag_without_v(self):
        self.assertEqual(calver.next_version("2.22.1", [], self.NOW)["tag"], "2.22.1-2026.09.06.1")

    def test_berlin_midnight_summer_winter_and_year_boundary(self):
        for instant, expected in [("2026-09-06T22:30:00+00:00", "2026.09.07"),
                                  ("2026-01-01T23:30:00+00:00", "2026.01.02"),
                                  ("2026-12-31T23:30:00+00:00", "2027.01.01")]:
            with self.subTest(instant=instant):
                self.assertEqual(calver.release_date(datetime.fromisoformat(instant)), expected)
        with self.assertRaises(ValueError):
            calver.release_date(datetime(2026, 9, 6))

    def test_rejects_invalid_versions_dates_and_counters(self):
        for tag in ["v2.22.1-beta", "v02.22.1", "v2.2", "v2.22.1; touch /tmp/no"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                calver.next_version(tag, [], self.NOW)
        for stamp in ["2026.02.30", "2026.13.01", "2026.9.06", "0000.01.01"]:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                calver.version_fields("v2.22.1", stamp, 1)
        for count in [0, -1, True, "1", 9007199254740992]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                calver.version_fields("v2.22.1", "2026.09.06", count)
        self.assertEqual(calver.version_fields("v2.22.1", "2028.02.29", 1)["tag"], "v2.22.1-2028.02.29.1")

    def test_all_reserved_tags_count_even_when_a_publication_failed(self):
        tags = ["v2.22.1-2026.09.06.1", "v2.22.1-2026.09.06.3"]
        self.assertEqual(calver.next_version("v2.22.1", tags, self.NOW)["tag"], "v2.22.1-2026.09.06.4")

    def test_plan_validation_detects_mismatched_public_and_package_versions(self):
        plan = {**calver.next_version("v2.22.1", [], self.NOW), "upstream": {"tag": "v2.22.1"}}
        calver.validate_plan_version(plan)
        for key, value in [("version", "2.22.1-2026.09.06.1"), ("tag", "v2.22.1-felix.123.1"),
                           ("pacmanVersion", "2.22.1-2026.09.06.1"), ("calver", {})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                calver.validate_plan_version({**plan, key: value})
        with self.assertRaises(ValueError):
            calver.validate_plan_version({**plan, "upstream": {"tag": "v2.22.2"}})

    def test_feed_has_exact_calver_url_and_valid_package_version(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            plan = {**calver.next_version("v2.22.1", [], self.NOW), "upstream": {"tag": "v2.22.1"}}
            (output / "build-info.json").write_text(json.dumps(plan))
            image = output / "Heroic-v2.22.1-2026.09.06.1-custom-x86_64.AppImage"
            image.write_bytes(b"test AppImage")
            calver.write_appimage_feed(output)
            info = json.loads((output / "latest-linux.yml").read_text())
            self.assertEqual(info["version"], "2.22.1-2026.9.6.1")
            self.assertIn("/v2.22.1-2026.09.06.1/Heroic-v2.22.1-2026.09.06.1-", info["path"])
            self.assertEqual(info["files"][0]["size"], image.stat().st_size)
            self.assertEqual(info["sha512"], info["files"][0]["sha512"])

    def test_feed_rejects_missing_mismatched_or_multiple_images(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            plan = {**calver.next_version("v2.22.1", [], self.NOW), "upstream": {"tag": "v2.22.1"}}
            (output / "build-info.json").write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                calver.write_appimage_feed(output)
            for architecture in ["x86_64", "arm64"]:
                (output / f"Heroic-{plan['tag']}-custom-{architecture}.AppImage").write_text("image")
            with self.assertRaises(ValueError):
                calver.write_appimage_feed(output)


if __name__ == "__main__":
    unittest.main()
