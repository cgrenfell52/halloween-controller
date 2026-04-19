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
        self.assertIn('data-command="SYS:STOP"', body)

    def test_service_page_renders_console_shell(self):
        response = self.client.get("/service")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("System State", body)
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
        response = self.client.post("/api/run_main", json={"mode": "TREAT"})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "TREAT")
        self.assertEqual(self.wait_for_last_result(), "DONE:DOOR_SEQUENCE")
        self.assertEqual(controller.state["recent_scenes"][-1]["scene"], "DOOR_SEQUENCE")

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
