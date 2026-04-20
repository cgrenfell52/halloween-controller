import importlib
import os
import sys
import time
import unittest
from pathlib import Path


os.environ["HALLOWEEN_AUDIO_DISABLED"] = "1"
os.environ["HALLOWEEN_USE_MOCK_ARDUINO"] = "1"
os.environ["HALLOWEEN_MOCK_SCENE_DELAY_SCALE"] = "0"


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
controller = importlib.import_module("app")


class FlaskRouteTests(unittest.TestCase):
    def setUp(self):
        controller.reset_runtime_state()
        controller.scene_bag = []
        controller.show_token_counter = 0
        controller.arduino = controller.MockArduino()
        controller.state["arduino_connected"] = True
        controller.state["system_status"] = "IDLE"
        controller.state["current_action"] = "NONE"
        controller.state["last_received_status"] = "STATUS:IDLE"
        self.client = controller.app.test_client()

    def wait_for_last_result(self, timeout_seconds=1):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if controller.state["last_result"] is not None:
                return controller.state["last_result"]
            time.sleep(0.01)
        return controller.state["last_result"]

    def wait_for_result(self, expected_result, timeout_seconds=1):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if controller.state["last_result"] == expected_result:
                return controller.state["last_result"]
            time.sleep(0.01)
        return controller.state["last_result"]

    def test_status_route_returns_controller_state(self):
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["system_status"], "IDLE")
        self.assertEqual(payload["arduino_mode"], "MOCK")
        self.assertIn("HEAD_1", payload["outputs"])

    def test_operator_page_renders_console_shell(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Prop Control System", body)
        self.assertIn("Trigger Control", body)
        self.assertIn('data-main="TRICK"', body)
        self.assertIn('data-command="RUN:TRICK_AIR_CANNON"', body)
        self.assertIn('data-command="SYS:STOP"', body)

    def test_service_page_renders_console_shell(self):
        response = self.client.get("/service")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("System State", body)
        self.assertIn("Quiet Time", body)
        self.assertIn("Service Toggles", body)
        self.assertIn("Scene Tests", body)
        self.assertIn('data-command="SYS:PING"', body)

    def test_run_main_rejects_invalid_mode(self):
        response = self.client.post("/api/run_main", json={"mode": "BOO"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    def test_run_command_rejects_invalid_command(self):
        response = self.client.post("/api/run_command", json={"command": "TOGGLE:TV_1"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "ERROR:INVALID_COMMAND:TOGGLE:TV_1")

    def test_run_command_dispatches_valid_toggle(self):
        response = self.client.post("/api/run_command", json={"command": "TOGGLE:HEAD_1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "command": "TOGGLE:HEAD_1"})
        self.assertEqual(self.wait_for_last_result(), "DONE:TOGGLE:HEAD_1")
        self.assertTrue(controller.state["outputs"]["HEAD_1"])
        self.assertTrue(any("WEB command requested: TOGGLE:HEAD_1" in entry for entry in controller.state["log"]))

    def test_service_button_commands_are_valid(self):
        for _label, command in controller.SERVICE_BUTTONS:
            with self.subTest(command=command):
                valid, error = controller.validate_command(command)
                self.assertTrue(valid, error)

    def test_run_command_dispatches_stop_and_latches_cancellation(self):
        controller.transact_command("TOGGLE:FOG")
        token = controller.begin_new_show()
        controller.state["last_result"] = None

        response = self.client.post("/api/run_command", json={"command": "SYS:STOP"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.wait_for_last_result(), "DONE:SYS:STOP")
        self.assertTrue(controller.is_show_cancelled(token))
        self.assertTrue(all(enabled is False for enabled in controller.state["outputs"].values()))

    def test_run_main_dispatches_treat_show(self):
        controller.scene_bag = ["TRICK_HEAD_1"]
        response = self.client.post("/api/run_main", json={"mode": "TREAT"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "TREAT")
        self.assertEqual(self.wait_for_result("DONE:TRICK_HEAD_1"), "DONE:TRICK_HEAD_1")
        self.assertEqual(controller.state["recent_scenes"][-2]["scene"], "DOOR_SEQUENCE")
        self.assertEqual(controller.state["recent_scenes"][-1]["scene"], "TRICK_HEAD_1")
        self.assertEqual(controller.state["recent_scenes"][-1]["mode"], "TREAT_TRICK")
        log = controller.state["log"]
        door_audio_index = next(i for i, entry in enumerate(log) if "AUDIO DISABLED -> skipped DOOR on DOOR" in entry)
        treat_audio_index = next(i for i, entry in enumerate(log) if "AUDIO DISABLED -> skipped TREAT on MAIN" in entry)
        door_scene_index = next(i for i, entry in enumerate(log) if "MOCK SEND -> RUN:DOOR_SEQUENCE" in entry)
        trick_scene_index = next(i for i, entry in enumerate(log) if "MOCK SEND -> RUN:TRICK_HEAD_1" in entry)
        self.assertLess(door_audio_index, door_scene_index)
        self.assertLess(treat_audio_index, door_scene_index)
        self.assertLess(door_scene_index, trick_scene_index)
        self.assertTrue(any("AUDIO DISABLED -> skipped SKINNY on HEAD_1" in entry for entry in log))
        self.assertFalse(any("AUDIO DISABLED -> skipped TRICK on MAIN" in entry for entry in log))

    def test_settings_route_updates_quiet_time(self):
        old_settings = controller.settings.copy()
        old_settings_file = controller.SETTINGS_FILE
        settings_path = REPO_ROOT / "test-settings.local.json"
        if settings_path.exists():
            settings_path.unlink()

        controller.SETTINGS_FILE = str(settings_path)
        try:
            response = self.client.post(
                "/api/settings",
                json={
                    "quiet_mode_enabled": True,
                    "quiet_start_time": "22:15",
                    "quiet_end_time": "07:30",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["ok"])
            self.assertEqual(controller.settings["quiet_start_time"], "22:15")
            self.assertEqual(controller.settings["quiet_end_time"], "07:30")
            self.assertTrue(settings_path.exists())
        finally:
            controller.settings.clear()
            controller.settings.update(old_settings)
            controller.SETTINGS_FILE = old_settings_file
            if settings_path.exists():
                settings_path.unlink()

    def test_password_auth_redirects_html_and_blocks_api(self):
        old_password = controller.ACCESS_PASSWORD
        controller.ACCESS_PASSWORD = "pumpkin"
        try:
            html_response = self.client.get("/")
            self.assertEqual(html_response.status_code, 302)
            self.assertIn("/login", html_response.headers["Location"])

            api_response = self.client.get("/api/status")
            self.assertEqual(api_response.status_code, 401)
            self.assertEqual(api_response.get_json()["error"], "AUTH_REQUIRED")
        finally:
            controller.ACCESS_PASSWORD = old_password

    def test_password_login_remembers_browser_session(self):
        old_password = controller.ACCESS_PASSWORD
        controller.ACCESS_PASSWORD = "pumpkin"
        try:
            login_response = self.client.post(
                "/login",
                data={"password": "pumpkin"},
                follow_redirects=False,
            )
            self.assertEqual(login_response.status_code, 302)

            response = self.client.get("/api/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["system_status"], "IDLE")
        finally:
            controller.ACCESS_PASSWORD = old_password


if __name__ == "__main__":
    unittest.main()
