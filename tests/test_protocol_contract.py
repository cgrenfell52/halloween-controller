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

    flask_stub.Flask = FakeFlask
    flask_stub.request = object()
    flask_stub.jsonify = lambda value=None, *args, **kwargs: value if value is not None else kwargs
    flask_stub.render_template = lambda template, **kwargs: template
    flask_stub.render_template_string = lambda template, **kwargs: template
    sys.modules.setdefault("flask", flask_stub)


install_flask_stub()
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
controller = importlib.import_module("app")
FIRMWARE_SOURCE = (REPO_ROOT / "arduino" / "firmware" / "firmware.ino").read_text()


class ProtocolContractTests(unittest.TestCase):
    def test_python_and_firmware_protocol_version_match(self):
        self.assertIn(f'static const char* PROTOCOL_VERSION = "{controller.PROTOCOL_VERSION}"', FIRMWARE_SOURCE)

    def test_python_and_firmware_baud_rate_match(self):
        self.assertIn(f"static const unsigned long SERIAL_BAUD = {controller.BAUD_RATE}", FIRMWARE_SOURCE)

    def test_all_controller_outputs_exist_in_firmware(self):
        for output_name in controller.OUTPUT_NAMES:
            with self.subTest(output=output_name):
                self.assertIn(f'"{output_name}"', FIRMWARE_SOURCE)
                self.assertIn(f"TOGGLE:{output_name}", FIRMWARE_SOURCE)

    def test_all_controller_scenes_exist_in_firmware(self):
        for scene_name in controller.SCENES:
            with self.subTest(scene=scene_name):
                self.assertIn(f"RUN:{scene_name}", FIRMWARE_SOURCE)
                self.assertIn(scene_name, FIRMWARE_SOURCE)

    def test_all_controller_system_commands_exist_in_firmware(self):
        for command in controller.ALLOWED_SYS_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, FIRMWARE_SOURCE)


if __name__ == "__main__":
    unittest.main()
