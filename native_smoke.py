"""Opt-in native packaged-app smoke test; ordinary gameplay never calls this."""
from pathlib import Path
import json

AUDIO_ASSETS = ("alien sound.mp3", "boss sound.mp3", "human hit.mp3",
                "laser shot.mp3", "missile shot.mp3")
CHECKS = ["window", "bundled-model", "bundled-audio-files", "rendered-frame",
          "primary-fire", "enemy-spawn", "shield-toggle", "restart"]


def require(condition, message):
    if not condition:
        raise RuntimeError("Native smoke failed: " + message)


def run(game, report_path):
    from panda3d.core import PNMImage
    require(game.win is not None and game.win.isValid(), "no native window")
    model = game.loader.loadModel("models/misc/sphere")
    require(not model.isEmpty(), "bundled Panda3D model missing")
    model.removeNode()
    for name in AUDIO_ASSETS:
        require(Path(game._asset_path(name)).stat().st_size > 0, "missing audio: " + name)
    # Exercise the real event handlers before advancing the normal task loop.
    game.fire_primary()
    require(game.cooldown_left > 0 and len(game.effects) > 0, "primary weapon did not fire")
    game.spawn_alien("scout")
    require(len(game.aliens) == 1, "enemy did not spawn")
    game.toggle_shield()
    require(game.shield_active, "shield did not raise")
    for _ in range(30):
        game.taskMgr.step()
    image = PNMImage()
    require(game.win.getScreenshot(image), "framebuffer readback failed")
    width, height = image.getXSize(), image.getYSize()
    require(width >= 320 and height >= 240, "framebuffer too small")
    # A live process or blank clear-color window is not a passing render.
    colors = {tuple(round(c, 3) for c in image.getXel(x, y))
              for y in range(0, height, max(1, height // 40))
              for x in range(0, width, max(1, width // 40))}
    require(len(colors) > 4, "rendered frame is blank")
    game.game_over = True
    game.health = 0
    game.restart_game()
    require(not game.game_over and game.health == game.max_health
            and not game.aliens and not game.projectiles and not game.shield_active,
            "restart did not restore gameplay")
    for _ in range(3):
        game.taskMgr.step()
    result = {"schema": 1, "status": "passed", "checks": CHECKS, "frames": 33,
              "width": width, "height": height, "sampled_colors": len(colors),
              "audio": "files-present; silent CI backend, playback not tested"}
    # Write only on complete success, then shut down normally.
    Path(report_path).write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    return result
