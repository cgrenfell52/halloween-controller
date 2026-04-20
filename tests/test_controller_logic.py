import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


os.environ["HALLOWEEN_AUDIO_DISABLED"] = "1"
os.environ["HALLOWEEN_USE_MOCK_ARDUINO"] = "1"
os.environ["HALLOWEEN_MOCK_SCENE_DELAY_SCALE"] = "0"


def install_flask_stub():
    if importlib.util.find_spec("flask") is not None:
        return

    flask_stub = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, name):
            self.name = name

        def route(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def run(self, *args, **kwargs):
            return None

    class FakeRequest:
        def get_json(self, force=False):
            return {}

    flask_stub.Flask = FakeFlask
    flask_stub.request = FakeRequest()
    flask_stub.jsonify = lambda value=None, *args, **kwargs: value if value is not None else kwargs
    flask_stub.render_template = lambda template, **kwargs: template
    flask_stub.render_template_string = lambda template, **kwargs: template
    sys.modules.setdefault("flask", flask_stub)


install_flask_stub()
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
controller = importlib.import_module("app")


class ControllerLogicTests(unittest.TestCase):
    def setUp(self):
        controller.reset_runtime_state()
        controller.scene_bag = []
        controller.show_token_counter = 0
        controller.arduino = controller.MockArduino()
        controller.state["arduino_connected"] = True
        controller.state["system_status"] = "IDLE"
        controller.state["current_action"] = "NONE"
        controller.state["last_received_status"] = "STATUS:IDLE"

    def test_validate_command_accepts_known_protocol_commands(self):
        for command in (
            "SYS:PING",
            "SYS:STOP",
            "TOGGLE:HEAD_1",
            "TOGGLE:FOG",
            "RUN:TRICK_HEAD_1",
            "RUN:DOOR_SEQUENCE",
        ):
            with self.subTest(command=command):
                self.assertEqual(controller.validate_command(command), (True, None))

    def test_validate_command_rejects_unknown_commands(self):
        valid, error = controller.validate_command("RUN:NOT_A_SCENE")

        self.assertFalse(valid)
        self.assertEqual(error, "ERROR:INVALID_COMMAND:RUN:NOT_A_SCENE")

    def test_scene_transaction_timeout_includes_scene_duration(self):
        self.assertGreaterEqual(controller.command_timeout_seconds("RUN:FOG_BURST"), 13.0)
        self.assertEqual(controller.expected_terminal_line("RUN:FOG_BURST"), "DONE:FOG_BURST")
        self.assertEqual(controller.command_timeout_seconds("SYS:PING"), 3.0)

    def test_serial_port_candidates_include_detected_fallback_ports(self):
        old_serial_port = controller.SERIAL_PORT
        old_glob = controller.glob.glob
        controller.SERIAL_PORT = "/dev/ttyACM0"
        controller.glob.glob = lambda pattern: {
            "/dev/ttyACM*": ["/dev/ttyACM1"],
            "/dev/ttyUSB*": ["/dev/ttyUSB0"],
        }.get(pattern, [])
        try:
            self.assertEqual(
                controller.serial_port_candidates(),
                ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"],
            )
        finally:
            controller.SERIAL_PORT = old_serial_port
            controller.glob.glob = old_glob

    def test_apply_protocol_line_updates_ready_status_state_and_done(self):
        controller.state["busy_until_epoch"] = 12345

        controller.apply_protocol_line("READY:PROP_CTRL_V2")
        controller.apply_protocol_line("STATUS:RUNNING_SCENE:TRICK_HEAD_1")
        controller.apply_protocol_line("STATE:HEAD_1:ON")
        controller.apply_protocol_line("DONE:TRICK_HEAD_1")
        controller.apply_protocol_line("STATUS:IDLE")

        self.assertEqual(controller.state["arduino_protocol_version"], "PROP_CTRL_V2")
        self.assertEqual(controller.state["outputs"]["HEAD_1"], True)
        self.assertEqual(controller.state["last_result"], "DONE:TRICK_HEAD_1")
        self.assertEqual(controller.state["system_status"], "IDLE")
        self.assertEqual(controller.state["current_action"], "NONE")
        self.assertFalse(controller.state["scene_active"])
        self.assertEqual(controller.state["busy_until_epoch"], 0)

    def test_mock_ping_and_status_transactions_update_controller_state(self):
        self.assertTrue(controller.transact_system_command("SYS:PING"))
        self.assertEqual(controller.state["arduino_protocol_version"], "PROP_CTRL_V2")
        self.assertEqual(controller.state["last_result"], "PONG")

        self.assertTrue(controller.transact_system_command("SYS:STATUS"))
        self.assertEqual(controller.state["system_status"], "IDLE")

    def test_mock_toggle_transaction_updates_output_state(self):
        self.assertTrue(controller.transact_command("TOGGLE:HEAD_1"))

        self.assertTrue(controller.state["outputs"]["HEAD_1"])
        self.assertEqual(controller.state["last_result"], "DONE:TOGGLE:HEAD_1")
        self.assertEqual(controller.state["system_status"], "IDLE")

    def test_mock_run_scene_transaction_tracks_done_and_recent_scene(self):
        self.assertTrue(controller.run_scene("TRICK_HEAD_1", "MANUAL_TEST"))

        self.assertEqual(controller.state["last_result"], "DONE:TRICK_HEAD_1")
        self.assertEqual(controller.state["system_status"], "IDLE")
        self.assertEqual(controller.state["recent_scenes"][-1]["scene"], "TRICK_HEAD_1")

    def test_manual_head_scenes_play_matching_audio_tracks(self):
        controller.run_manual_command("RUN:TRICK_HEAD_1")
        self.assertTrue(any("AUDIO DISABLED -> skipped SKINNY on HEAD_1" in entry for entry in controller.state["log"]))
        self.assertFalse(any("AUDIO DISABLED -> skipped TRICK on MAIN" in entry for entry in controller.state["log"]))

        controller.reset_runtime_state()
        controller.arduino = controller.MockArduino()
        controller.state["system_status"] = "IDLE"
        controller.run_manual_command("RUN:TRICK_HEAD_2")
        self.assertTrue(any("AUDIO DISABLED -> skipped HAG on HEAD_2" in entry for entry in controller.state["log"]))
        self.assertFalse(any("AUDIO DISABLED -> skipped TRICK on MAIN" in entry for entry in controller.state["log"]))

    def test_both_heads_scene_plays_both_head_audio_tracks(self):
        controller.run_manual_command("RUN:TRICK_BOTH_HEADS")

        self.assertTrue(any("AUDIO DISABLED -> skipped SKINNY on HEAD_1" in entry for entry in controller.state["log"]))
        self.assertTrue(any("AUDIO DISABLED -> skipped HAG on HEAD_2" in entry for entry in controller.state["log"]))
        self.assertFalse(any("AUDIO DISABLED -> skipped TRICK on MAIN" in entry for entry in controller.state["log"]))

    def test_trick_show_plays_main_trick_audio(self):
        token = controller.begin_new_show()

        controller.run_show("TRICK", token)

        self.assertTrue(any("AUDIO DISABLED -> skipped TRICK on MAIN" in entry for entry in controller.state["log"]))

    def test_quiet_time_filters_loud_trick_scenes(self):
        old_settings = controller.settings.copy()
        old_current_minutes = controller.current_minutes
        try:
            controller.settings.update(
                {
                    "quiet_mode_enabled": True,
                    "quiet_start_time": "21:00",
                    "quiet_end_time": "08:00",
                }
            )
            controller.current_minutes = lambda: (22 * 60)

            selected_scenes = {controller.choose_trick_scene() for _ in range(3)}

            self.assertTrue(selected_scenes)
            self.assertTrue(selected_scenes.isdisjoint(controller.QUIET_EXCLUDED_TRICK_SCENES))
            self.assertEqual(set(controller.state["trick_bag_available_scenes"]), {
                "TRICK_HEAD_1",
                "TRICK_HEAD_2",
                "TRICK_BOTH_HEADS",
            })
            self.assertTrue(controller.state["quiet_mode_active"])
        finally:
            controller.settings.clear()
            controller.settings.update(old_settings)
            controller.current_minutes = old_current_minutes

    def test_regular_time_uses_full_trick_bag(self):
        old_settings = controller.settings.copy()
        old_current_minutes = controller.current_minutes
        try:
            controller.settings.update(
                {
                    "quiet_mode_enabled": True,
                    "quiet_start_time": "21:00",
                    "quiet_end_time": "08:00",
                }
            )
            controller.current_minutes = lambda: (12 * 60)

            controller.choose_trick_scene()

            self.assertEqual(set(controller.state["trick_bag_available_scenes"]), set(controller.TRICK_SCENES))
            self.assertFalse(controller.state["quiet_mode_active"])
        finally:
            controller.settings.clear()
            controller.settings.update(old_settings)
            controller.current_minutes = old_current_minutes

    def test_stop_command_cancels_show_and_turns_outputs_off(self):
        controller.transact_command("TOGGLE:HEAD_1")
        controller.transact_command("TOGGLE:FOG")
        token = controller.begin_new_show()

        controller.run_manual_command("SYS:STOP")

        self.assertTrue(controller.is_show_cancelled(token))
        self.assertTrue(all(enabled is False for enabled in controller.state["outputs"].values()))
        self.assertEqual(controller.state["last_result"], "DONE:SYS:STOP")
        self.assertEqual(controller.state["system_status"], "IDLE")

    def test_busy_show_request_does_not_replace_active_token(self):
        token = controller.begin_new_show()
        controller.state["scene_active"] = True
        controller.state["system_status"] = "RUNNING_SCENE"

        self.assertIsNone(controller.start_show_request("TREAT", "GPIO"))

        self.assertEqual(controller.state["active_show_token"], token)
        self.assertEqual(controller.state["last_result"], "ERROR:BUSY")

    def test_busy_mock_arduino_rejects_overlapping_scene(self):
        controller.arduino.system_state = "RUNNING_SCENE"

        self.assertFalse(controller.transact_command("RUN:TRICK_HEAD_1"))
        self.assertEqual(controller.state["last_result"], "ERROR:BUSY")

    def test_invalid_transaction_is_rejected_before_hardware(self):
        self.assertFalse(controller.transact_command("TOGGLE:TV_1"))
        self.assertEqual(controller.state["last_result"], "ERROR:INVALID_COMMAND:TOGGLE:TV_1")

    def test_no_reply_is_reported_as_error(self):
        self.assertFalse(controller._process_command_lines("RUN:TRICK_HEAD_1", []))
        self.assertEqual(controller.state["last_result"], "ERROR:NO_REPLY")

    def test_unexpected_done_is_reported_for_scene_command(self):
        lines = ["STATUS:RUNNING_SCENE:TRICK_HEAD_1", "DONE:DOOR_SEQUENCE", "STATUS:IDLE"]

        self.assertFalse(controller._process_command_lines("RUN:TRICK_HEAD_1", lines))
        self.assertEqual(controller.state["last_result"], "ERROR:UNEXPECTED_REPLY")

    def test_error_reply_wins_over_done_reply(self):
        lines = ["DONE:TRICK_HEAD_1", "ERROR:BUSY"]

        self.assertFalse(controller._process_command_lines("RUN:TRICK_HEAD_1", lines))
        self.assertEqual(controller.state["last_result"], "ERROR:BUSY")

    def test_malformed_state_line_does_not_change_outputs(self):
        controller.state["outputs"]["HEAD_1"] = False

        controller.apply_protocol_line("STATE:HEAD_1")
        controller.apply_protocol_line("STATE:HEAD_1:MAYBE")
        controller.apply_protocol_line("STATE:UNKNOWN:ON")

        self.assertFalse(controller.state["outputs"]["HEAD_1"])
        self.assertNotIn("UNKNOWN", controller.state["outputs"])

    def test_unknown_status_is_recorded_without_marking_scene_active(self):
        controller.apply_protocol_line("STATUS:CALIBRATING")

        self.assertEqual(controller.state["system_status"], "CALIBRATING")
        self.assertEqual(controller.state["current_action"], "NONE")
        self.assertFalse(controller.state["scene_active"])


if __name__ == "__main__":
    unittest.main()
