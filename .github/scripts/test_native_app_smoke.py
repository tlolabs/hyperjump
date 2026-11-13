"""Unit tests of smoke assertions, with Panda/window objects mocked (no Mac app)."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("app_native_smoke", Path(__file__).resolve().parents[2] / "native_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class Image:
    def getXSize(self): return 640
    def getYSize(self): return 480
    def getXel(self, x, y): return (x / 640, y / 480, 0.2)


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in smoke.AUDIO_ASSETS:
            (self.root / name).write_bytes(b"mp3 fixture")
        self.report = self.root / "result.json"
        self.game = MagicMock()
        self.game._asset_path.side_effect = lambda name: str(self.root / name)
        self.game.win.isValid.return_value = True
        self.game.win.getScreenshot.return_value = True
        self.game.loader.loadModel.return_value.isEmpty.return_value = False
        self.game.cooldown_left = 0
        self.game.effects = []
        self.game.aliens = []
        self.game.projectiles = []
        self.game.shield_active = False
        self.game.max_health = 6
        def fire():
            self.game.cooldown_left = 0.14
            self.game.effects.append("muzzle")
        def spawn(kind):
            self.game.aliens.append(kind)
        def shield():
            self.game.shield_active = True
        def restart():
            self.game.game_over = False
            self.game.health = self.game.max_health
            self.game.aliens.clear()
            self.game.projectiles.clear()
            self.game.shield_active = False
        self.game.fire_primary.side_effect = fire
        self.game.spawn_alien.side_effect = spawn
        self.game.toggle_shield.side_effect = shield
        self.game.restart_game.side_effect = restart
        self.panda = patch.dict(sys.modules, {"panda3d.core": SimpleNamespace(PNMImage=Image)})
        self.panda.start()

    def tearDown(self):
        self.panda.stop()
        self.temp.cleanup()

    def test_complete_smoke_writes_report_after_all_assertions(self):
        result = smoke.run(self.game, self.report)
        self.assertEqual(result, json.loads(self.report.read_text()))
        self.assertEqual(self.game.taskMgr.step.call_count, 33)
        self.assertEqual(result["checks"], smoke.CHECKS)
        self.assertEqual(result["status"], "passed")
        from native_package import validate_smoke
        validate_smoke(result)

    def test_missing_native_window_fails_without_report(self):
        self.game.win.isValid.return_value = False
        with self.assertRaises(RuntimeError): smoke.run(self.game, self.report)
        self.assertFalse(self.report.exists())

    def test_missing_model_fails_without_report(self):
        self.game.loader.loadModel.return_value.isEmpty.return_value = True
        with self.assertRaises(RuntimeError): smoke.run(self.game, self.report)
        self.assertFalse(self.report.exists())

    def test_missing_audio_fails_without_report(self):
        (self.root / smoke.AUDIO_ASSETS[0]).unlink()
        with self.assertRaises(OSError): smoke.run(self.game, self.report)
        self.assertFalse(self.report.exists())

    def test_broken_fire_spawn_shield_restart_fail(self):
        for method in ("fire_primary", "spawn_alien", "toggle_shield", "restart_game"):
            with self.subTest(method=method):
                # Reset to avoid one case masking another.
                self.game.cooldown_left, self.game.effects, self.game.aliens = 0, [], []
                self.game.shield_active = False
                callback = getattr(self.game, method).side_effect
                getattr(self.game, method).side_effect = lambda *args: None
                try:
                    with self.assertRaises(RuntimeError): smoke.run(self.game, self.report)
                    self.assertFalse(self.report.exists())
                finally:
                    getattr(self.game, method).side_effect = callback

    def test_blank_frame_is_failure_not_process_liveness_success(self):
        with patch.object(Image, "getXel", return_value=(0, 0, 0)):
            with self.assertRaises(RuntimeError): smoke.run(self.game, self.report)
        self.assertFalse(self.report.exists())

    def test_failed_readback_fails(self):
        self.game.win.getScreenshot.return_value = False
        with self.assertRaises(RuntimeError): smoke.run(self.game, self.report)
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
