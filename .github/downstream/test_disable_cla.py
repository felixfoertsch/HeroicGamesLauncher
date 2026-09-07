"""Exercise repeated CLA maintenance without making GitHub requests."""
import json
import os
import unittest
from unittest.mock import call, patch

import disable_cla
from calver import REPOSITORY

READ = ("api", f"repos/{REPOSITORY}/actions/workflows/cla.yml")
DISABLE = ("workflow", "disable", "cla.yml", "--repo", REPOSITORY)


def state(value):
    return json.dumps({"state": value})


class DisableClaTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": REPOSITORY})
        environment.start()
        self.addCleanup(environment.stop)

    def test_already_manually_disabled_is_a_read_only_success(self):
        with patch.object(disable_cla, "gh", return_value=state("disabled_manually")) as gh:
            self.assertEqual(disable_cla.ensure_disabled(), "disabled_manually")
        gh.assert_called_once_with(*READ)

    def test_already_inactive_is_a_read_only_success(self):
        with patch.object(disable_cla, "gh", return_value=state("disabled_inactivity")) as gh:
            self.assertEqual(disable_cla.ensure_disabled(), "disabled_inactivity")
        gh.assert_called_once_with(*READ)

    def test_disables_active_workflow_and_verifies_result(self):
        with patch.object(disable_cla, "gh", side_effect=[state("active"), "", state("disabled_manually")]) as gh:
            self.assertEqual(disable_cla.ensure_disabled(), "disabled_manually")
        self.assertEqual(gh.call_args_list, [call(*READ), call(*DISABLE), call(*READ)])

    def test_concurrent_disable_is_accepted_only_after_verification(self):
        with patch.object(disable_cla, "gh", side_effect=[state("active"), RuntimeError("Already disabled"), state("disabled_manually")]) as gh:
            self.assertEqual(disable_cla.ensure_disabled(), "disabled_manually")
        self.assertEqual(gh.call_args_list, [call(*READ), call(*DISABLE), call(*READ)])

    def test_permission_failure_is_not_ignored(self):
        error = RuntimeError("Permission denied")
        with patch.object(disable_cla, "gh", side_effect=[state("active"), error, state("active")]):
            with self.assertRaises(RuntimeError) as caught:
                disable_cla.ensure_disabled()
        self.assertIs(caught.exception, error)

    def test_successful_write_must_actually_disable_workflow(self):
        with patch.object(disable_cla, "gh", side_effect=[state("active"), "", state("active")]):
            with self.assertRaisesRegex(RuntimeError, "still active"):
                disable_cla.ensure_disabled()

    def test_unknown_state_stops_without_writing(self):
        with patch.object(disable_cla, "gh", return_value=state("unexpected")) as gh:
            with self.assertRaisesRegex(ValueError, "Unexpected CLA workflow state"):
                disable_cla.ensure_disabled()
        gh.assert_called_once_with(*READ)

    def test_read_failure_stops_without_writing(self):
        with patch.object(disable_cla, "gh", side_effect=RuntimeError("Read failed")) as gh:
            with self.assertRaisesRegex(RuntimeError, "Read failed"):
                disable_cla.ensure_disabled()
        gh.assert_called_once_with(*READ)

    def test_wrong_repository_is_rejected_before_any_request(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "Heroic-Games-Launcher/HeroicGamesLauncher"}):
            with patch.object(disable_cla, "gh") as gh:
                with self.assertRaisesRegex(ValueError, "restricted"):
                    disable_cla.ensure_disabled()
        gh.assert_not_called()

    def test_failed_verification_read_is_not_ignored(self):
        with patch.object(disable_cla, "gh", side_effect=[state("active"), "", RuntimeError("Verification failed")]):
            with self.assertRaisesRegex(RuntimeError, "Verification failed"):
                disable_cla.ensure_disabled()


if __name__ == "__main__":
    unittest.main()
