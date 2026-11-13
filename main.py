from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight,
    CardMaker,
    DirectionalLight,
    LineSegs,
    NodePath,
    TextNode,
    TransparencyAttrib,
    Vec3,
    WindowProperties,
    loadPrcFileData,
)

loadPrcFileData(
    "",
    "\n".join(
        [
            "fullscreen 0",
            "undecorated 0",
            "win-size 1600 900",
            "sync-video 1",
            "window-title Hyper Jump",
        ]
    ),
)


@dataclass
class Alien:
    root: NodePath
    velocity: Vec3
    radius: float
    hp: int
    kind: str
    attack_cooldown: float = 0.0


@dataclass
class Star:
    node: NodePath
    speed: float


@dataclass
class Projectile:
    root: NodePath
    velocity: Vec3
    radius: float
    damage: int
    ttl: float
    kind: str
    source: str
    target: Alien | None = None


@dataclass
class PowerBubble:
    root: NodePath
    kind: str
    ttl: float
    radius: float = 2.2


@dataclass
class LatchedMouth:
    root: NodePath
    damage_timer: float = 0.75


class AlienShooterGame(ShowBase):
    def __init__(self) -> None:
        super().__init__()

        self.disableMouse()
        self.setBackgroundColor(0.01, 0.01, 0.04, 1.0)

        self.accept("escape", self.userExit)
        self.accept("mouse1", self.fire_primary)
        self.accept("space", self.fire_primary)
        self.accept("f", self.fire_missile)
        self.accept("g", self.fire_bubble_gun)
        self.accept("b", self.launch_bomb)
        self.accept("e", self.toggle_shield)
        self.accept("r", self.restart_game)

        self.turn_speed = 70.0
        self.pitch_speed = 55.0
        self.fire_cooldown = 0.14
        self.cooldown_left = 0.0
        self.spawn_timer = 0.0
        self.spawn_interval = 1.15
        self.alien_speed = 10.0
        self.max_health = 6.0
        self.health = self.max_health
        self.score = 0
        self.bombs = 3
        self.missiles = 0
        self.bubble_ammo = 0
        self.shield_energy = 100.0
        self.shield_active = False
        self.shield_regen_delay = 0.0
        self.level = 1
        self.game_over = False
        self.flash_timer = 0.0
        self.bomb_flash_timer = 0.0
        self.crosshair_size = 0.018
        self.stage = "assault"
        self.kills_this_level = 0
        self.assault_target = 12
        self.boss_spawned = False
        self.add_spawn_timer = 0.0
        self.powerup_spawn_timer = 0.0
        self.shield_purge_progress = 0.0
        self.star_speed = 48.0
        self.approach_speed = 54.0
        self.planet_target_y = 130.0

        self.aliens: list[Alien] = []
        self.effects: list[NodePath] = []
        self.stars: list[Star] = []
        self.projectiles: list[Projectile] = []
        self.power_bubbles: list[PowerBubble] = []
        self.latched_mouths: list[LatchedMouth] = []
        self.boss: Alien | None = None

        self.camera.setPos(0, 0, 0)
        self.camera.setHpr(0, 0, 0)
        self.camLens.setFov(85)
        self.camLens.setNearFar(0.1, 700)

        self._configure_mouse()
        self._build_scene()
        self._build_ui()
        self._load_audio()
        self._refresh_ui()

        self.taskMgr.add(self.update, "update")

    def _configure_mouse(self) -> None:
        props = WindowProperties()
        props.setFullscreen(False)
        props.setUndecorated(False)
        props.setCursorHidden(True)
        props.setTitle("Hyper Jump")
        self.win.requestProperties(props)
        self.center_pointer()

    def _asset_path(self, filename: str) -> str:
        if hasattr(sys, "_MEIPASS"):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).resolve().parent
        return str(base_path / filename)

    def _build_scene(self) -> None:
        self.space = self.render.attachNewNode("space")
        self.aliens_root = self.render.attachNewNode("aliens")
        self.effects_root = self.render.attachNewNode("effects")
        self.projectiles_root = self.render.attachNewNode("projectiles")
        self.powerup_root = self.render.attachNewNode("powerups")
        self._add_lighting()
        self._add_starfield()
        self._build_planet()

    def _add_lighting(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.45, 0.45, 0.55, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        key = DirectionalLight("key")
        key.setColor((0.92, 0.96, 1.0, 1))
        key_np = self.render.attachNewNode(key)
        key_np.setHpr(-20, -35, 0)
        self.render.setLight(key_np)

    def _add_starfield(self) -> None:
        sphere = self.loader.loadModel("models/misc/sphere")
        for _ in range(240):
            star = sphere.copyTo(self.space)
            self._reset_star(star, initial=True)
            self.stars.append(Star(node=star, speed=random.uniform(28.0, 95.0)))

    def _reset_star(self, star: NodePath, initial: bool = False) -> None:
        x = random.uniform(-170.0, 170.0)
        z = random.uniform(-95.0, 95.0)
        y = random.uniform(-40.0, 260.0) if initial else random.uniform(180.0, 260.0)
        star.setPos(x, y, z)
        scale = random.uniform(0.03, 0.15)
        brightness = random.uniform(0.55, 1.0)
        star.setScale(scale)
        star.setColor(brightness, brightness, brightness, 1.0)
        star.setLightOff()

    def _build_planet(self) -> None:
        self.planet = self.loader.loadModel("models/misc/sphere")
        self.planet.reparentTo(self.render)
        self.planet.setScale(24.0)
        self.planet.setPos(0, 420.0, -40.0)
        self.planet.setColor(0.25, 0.55, 0.95, 1.0)
        self.planet.hide()

        cloud = self.loader.loadModel("models/misc/sphere")
        cloud.reparentTo(self.planet)
        cloud.setScale(1.03)
        cloud.setColor(0.9, 0.95, 1.0, 0.18)
        cloud.setTransparency(TransparencyAttrib.MAlpha)

    def _build_ui(self) -> None:
        self.score_text = OnscreenText(
            text="Score: 0",
            pos=(-1.28, 0.92),
            scale=0.052,
            fg=(0.9, 0.96, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.health_text = OnscreenText(
            text="Hull: 6",
            pos=(-1.28, 0.84),
            scale=0.052,
            fg=(1.0, 0.6, 0.6, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.shield_text = OnscreenText(
            text="Shield: 100%",
            pos=(-1.28, 0.76),
            scale=0.052,
            fg=(0.5, 0.88, 1.0, 1.0),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.weapons_text = OnscreenText(
            text="LMB/Space Cannon  |  F Missile  |  G Bubble  |  B Bomb  |  E Shield",
            pos=(0, -0.92),
            scale=0.045,
            fg=(0.85, 0.95, 1.0, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.ammo_text = OnscreenText(
            text="Bombs: 3  Missiles: 0  Bubbles: 0",
            pos=(1.28, 0.92),
            scale=0.05,
            fg=(1.0, 0.9, 0.45, 1.0),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.stage_text = OnscreenText(
            text="Sector: Alien Front",
            pos=(1.28, 0.84),
            scale=0.048,
            fg=(0.72, 0.92, 1.0, 1.0),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.nav_text = OnscreenText(
            text="NAV: Sweep for hostiles",
            pos=(1.28, 0.76),
            scale=0.046,
            fg=(0.7, 1.0, 0.86, 1.0),
            align=TextNode.ARight,
            mayChange=True,
        )
        self.attached_text = OnscreenText(
            text="Attached: 0",
            pos=(0, 0.74),
            scale=0.054,
            fg=(1.0, 0.35, 0.35, 0.25),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.message_text = OnscreenText(
            text="Shoot power bubbles to collect upgrades",
            pos=(0, -0.8),
            scale=0.068,
            fg=(1.0, 0.92, 0.75, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.boss_text = OnscreenText(
            text="",
            pos=(0, 0.9),
            scale=0.06,
            fg=(1.0, 0.42, 0.42, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self.game_over_text = OnscreenText(
            text="",
            pos=(0, 0.08),
            scale=0.13,
            fg=(1.0, 0.85, 0.85, 1.0),
            align=TextNode.ACenter,
            mayChange=True,
        )

        self.flash_card = self._make_flash_card((1.0, 0.2, 0.2, 0.0), 20)
        self.bomb_flash_card = self._make_flash_card((0.7, 0.95, 1.0, 0.0), 19)
        self.shield_card = self._make_flash_card((0.2, 0.8, 1.0, 0.0), 18)
        self.game_over_card = self._make_flash_card((0.02, 0.02, 0.05, 0.0), 21)
        self.crosshair = self._make_crosshair()
        self.cockpit = self._make_cockpit_hud()
        self.progress_bar = self._make_progress_bar()
        self.attached_overlay = self._make_attached_overlay()

    def _load_audio(self) -> None:
        self.sounds = {
            "laser": self.loader.loadSfx(self._asset_path("laser shot.mp3")),
            "missile": self.loader.loadSfx(self._asset_path("missile shot.mp3")),
            "human_hit": self.loader.loadSfx(self._asset_path("human hit.mp3")),
            "boss": self.loader.loadSfx(self._asset_path("boss sound.mp3")),
            "alien": self.loader.loadSfx(self._asset_path("alien sound.mp3")),
        }

        self.sounds["laser"].setVolume(0.45)
        self.sounds["missile"].setVolume(0.7)
        self.sounds["human_hit"].setVolume(0.75)
        self.sounds["boss"].setVolume(0.9)
        self.sounds["alien"].setVolume(0.45)

    def _play_sound(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is None:
            return
        sound.stop()
        sound.play()

    def _make_flash_card(self, color: tuple[float, float, float, float], sort: int) -> NodePath:
        card = CardMaker(f"flash-{sort}")
        card.setFrameFullscreenQuad()
        node = self.aspect2d.attachNewNode(card.generate())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setColor(*color)
        node.setBin("fixed", sort)
        node.setDepthTest(False)
        node.setDepthWrite(False)
        return node

    def _make_crosshair(self) -> NodePath:
        lines = LineSegs("crosshair")
        lines.setThickness(2.0)
        lines.setColor(0.85, 0.96, 1.0, 1.0)
        s = self.crosshair_size
        gap = s * 0.35
        ring = s * 0.55

        lines.moveTo(-s, 0, 0)
        lines.drawTo(-gap, 0, 0)
        lines.moveTo(s, 0, 0)
        lines.drawTo(gap, 0, 0)
        lines.moveTo(0, 0, -s)
        lines.drawTo(0, 0, -gap)
        lines.moveTo(0, 0, s)
        lines.drawTo(0, 0, gap)

        step_count = 20
        for step in range(step_count):
            a0 = (math.pi * 2.0 * step) / step_count
            a1 = (math.pi * 2.0 * (step + 1)) / step_count
            lines.moveTo(math.cos(a0) * ring, 0, math.sin(a0) * ring)
            lines.drawTo(math.cos(a1) * ring, 0, math.sin(a1) * ring)

        node = self.aspect2d.attachNewNode(lines.create())
        node.setBin("fixed", 30)
        node.setDepthTest(False)
        node.setDepthWrite(False)
        return node

    def _make_cockpit_hud(self) -> NodePath:
        lines = LineSegs("cockpit")
        lines.setThickness(2.0)
        lines.setColor(0.3, 0.88, 1.0, 0.88)

        lines.moveTo(-1.05, 0, -0.85)
        lines.drawTo(-0.72, 0, -0.5)
        lines.drawTo(-0.38, 0, -0.42)
        lines.moveTo(1.05, 0, -0.85)
        lines.drawTo(0.72, 0, -0.5)
        lines.drawTo(0.38, 0, -0.42)

        lines.moveTo(-1.22, 0, 0.72)
        lines.drawTo(-0.9, 0, 0.72)
        lines.moveTo(1.22, 0, 0.72)
        lines.drawTo(0.9, 0, 0.72)

        lines.moveTo(-0.3, 0, -0.92)
        lines.drawTo(-0.14, 0, -0.75)
        lines.drawTo(0.14, 0, -0.75)
        lines.drawTo(0.3, 0, -0.92)

        node = self.aspect2d.attachNewNode(lines.create())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", 28)
        node.setDepthTest(False)
        node.setDepthWrite(False)
        return node

    def _make_progress_bar(self) -> NodePath:
        bar = CardMaker("progress")
        bar.setFrame(-0.25, 0.25, -0.015, 0.015)
        node = self.aspect2d.attachNewNode(bar.generate())
        node.setPos(0, 0, 0.8)
        node.setColor(0.2, 0.9, 1.0, 0.7)
        node.setTransparency(TransparencyAttrib.MAlpha)
        return node

    def _make_attached_overlay(self) -> NodePath:
        lines = LineSegs("attached-overlay")
        lines.setThickness(3.0)
        lines.setColor(1.0, 0.32, 0.32, 0.0)
        for x_sign in (-1, 1):
            lines.moveTo(0.8 * x_sign, 0, 0.6)
            lines.drawTo(1.1 * x_sign, 0, 0.84)
            lines.moveTo(0.8 * x_sign, 0, -0.6)
            lines.drawTo(1.1 * x_sign, 0, -0.84)
        node = self.aspect2d.attachNewNode(lines.create())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", 31)
        node.setDepthTest(False)
        node.setDepthWrite(False)
        return node

    def center_pointer(self) -> None:
        pointer = self.win.getPointer(0)
        self.center_x = self.win.getXSize() // 2
        self.center_y = self.win.getYSize() // 2
        if pointer.getX() != self.center_x or pointer.getY() != self.center_y:
            self.win.movePointer(0, self.center_x, self.center_y)

    def restart_game(self) -> None:
        if not self.game_over:
            return

        self._clear_enemies()
        self._clear_effects()
        self._clear_projectiles()
        self._clear_power_bubbles()
        self._clear_latched_mouths()

        self.camera.setHpr(0, 0, 0)
        self.cooldown_left = 0.0
        self.spawn_timer = 0.0
        self.spawn_interval = 1.15
        self.alien_speed = 10.0
        self.health = self.max_health
        self.score = 0
        self.bombs = 3
        self.missiles = 0
        self.bubble_ammo = 0
        self.shield_energy = 100.0
        self.shield_active = False
        self.shield_regen_delay = 0.0
        self.level = 1
        self.game_over = False
        self.flash_timer = 0.0
        self.bomb_flash_timer = 0.0
        self.stage = "assault"
        self.kills_this_level = 0
        self.boss_spawned = False
        self.add_spawn_timer = 0.0
        self.powerup_spawn_timer = 0.0
        self.shield_purge_progress = 0.0
        self.star_speed = 48.0
        self.message_text.setText("Shoot power bubbles to collect upgrades")
        self.boss_text.setText("")
        self.game_over_text.setText("")
        self.flash_card.setColor(1.0, 0.2, 0.2, 0.0)
        self.bomb_flash_card.setColor(0.7, 0.95, 1.0, 0.0)
        self.shield_card.setColor(0.2, 0.8, 1.0, 0.0)
        self.game_over_card.setColor(0.02, 0.02, 0.05, 0.0)
        self.planet.setPos(0, 420.0, -40.0)
        self.planet.hide()
        self._refresh_ui()
        self.center_pointer()

    def _clear_enemies(self) -> None:
        for alien in self.aliens:
            alien.root.removeNode()
        self.aliens.clear()
        self.boss = None

    def _clear_effects(self) -> None:
        for effect in self.effects:
            effect.removeNode()
        self.effects.clear()

    def _clear_projectiles(self) -> None:
        for projectile in self.projectiles:
            projectile.root.removeNode()
        self.projectiles.clear()

    def _clear_power_bubbles(self) -> None:
        for bubble in self.power_bubbles:
            bubble.root.removeNode()
        self.power_bubbles.clear()

    def _clear_latched_mouths(self) -> int:
        cleared = 0
        for mouth in self.latched_mouths:
            mouth.root.removeNode()
            cleared += 1
        self.latched_mouths.clear()
        return cleared

    def spawn_alien(self, kind: str = "scout") -> None:
        if self.game_over:
            return

        is_boss = kind == "boss"
        root = self.aliens_root.attachNewNode(f"{kind}-root")

        if is_boss:
            root.setPos(0, 150.0, 8.0)
            body_scale = (7.2, 5.8, 5.0)
            color = (0.65, 0.2, 0.82, 1.0)
            radius = 7.6
            hp = 38
            speed = 4.0
            cooldown = 1.2
        else:
            root.setPos(
                random.uniform(-24.0, 24.0),
                random.uniform(85.0, 125.0),
                random.uniform(-16.0, 16.0),
            )
            if kind == "escort":
                body_scale = (1.7, 1.3, 1.3)
                color = (0.92, 0.32, 0.18, 1.0)
                hp = 2
                cooldown = 2.0
            elif kind == "brute":
                body_scale = (1.95, 1.55, 1.45)
                color = (1.0, 0.5, 0.14, 1.0)
                hp = 3
                cooldown = 1.8
            else:
                body_scale = (1.5, 1.2, 1.1)
                color = (0.45, 0.95, 0.35, 1.0)
                hp = 1
                cooldown = 2.6
            radius = 2.25 if kind == "brute" else 1.8
            speed = self.alien_speed * 0.82 if kind == "brute" else self.alien_speed

        self._build_alien_model(root, kind, body_scale, color)
        velocity = (Vec3(0, 0, 0) - root.getPos()).normalized() * speed
        alien = Alien(root=root, velocity=velocity, radius=radius, hp=hp, kind=kind, attack_cooldown=cooldown)
        self.aliens.append(alien)

        if is_boss:
            self._play_sound("boss")
            self.boss = alien
            self.boss_spawned = True
            self.boss_text.setText(f"Overmind Hull: {alien.hp}")
            self.message_text.setText("Boss contact. Shield the cockpit.")
        else:
            self._play_sound("alien")

    def _build_alien_model(
        self,
        root: NodePath,
        kind: str,
        body_scale: tuple[float, float, float],
        color: tuple[float, float, float, float],
    ) -> None:
        body = self.loader.loadModel("models/misc/sphere")
        body.reparentTo(root)
        body.setScale(*body_scale)
        body.setColor(*color)

        eye_model = self.loader.loadModel("models/misc/sphere")
        is_boss = kind == "boss"
        is_brute = kind == "brute"
        eye_scale = 0.6 if is_boss else 0.3 if is_brute else 0.22
        eye_y = -4.1 if is_boss else -1.12 if is_brute else -0.98
        eye_x = 1.65 if is_boss else 0.54 if is_brute else 0.42
        for sign in (-1, 1):
            eye = eye_model.copyTo(root)
            eye.setScale(eye_scale)
            eye.setPos(sign * eye_x, eye_y, 0.78 if is_boss else 0.34 if is_brute else 0.2)
            eye.setColor(1.0, 0.12, 0.12, 1.0)
            eye.setLightOff()

        brow_model = self.loader.loadModel("models/misc/sphere")
        for sign in (-1, 1):
            brow = brow_model.copyTo(root)
            brow.setScale(0.85, 0.16, 0.12) if is_boss else brow.setScale(0.34, 0.08, 0.06)
            brow.setPos(sign * (1.85 if is_boss else 0.6 if is_brute else 0.46), -3.85 if is_boss else -0.92, 1.55 if is_boss else 0.5 if is_brute else 0.32)
            brow.setHpr(0, 0, -24 * sign)
            brow.setColor(0.08, 0.02, 0.02, 1.0)

        mouth = self.loader.loadModel("models/misc/sphere")
        mouth.reparentTo(root)
        mouth.setScale(2.6, 2.3, 0.9) if is_boss else mouth.setScale(0.82, 0.86, 0.26) if is_brute else mouth.setScale(0.68, 0.72, 0.22)
        mouth.setPos(0, -4.95, -0.8) if is_boss else mouth.setPos(0, -1.45, -0.24) if is_brute else mouth.setPos(0, -1.24, -0.2)
        mouth.setColor(0.12, 0.02, 0.02, 1.0)

        tooth_model = self.loader.loadModel("models/misc/sphere")
        tooth_offsets = (-1.8, -0.9, 0.0, 0.9, 1.8) if is_boss else (-0.34, -0.12, 0.12, 0.34) if is_brute else (-0.24, 0.0, 0.24)
        for offset in tooth_offsets:
            tooth = tooth_model.copyTo(root)
            tooth.setScale(0.22, 0.18, 0.68) if is_boss else tooth.setScale(0.08, 0.06, 0.22) if is_brute else tooth.setScale(0.05, 0.05, 0.16)
            tooth.setPos(offset, -4.35, -0.06) if is_boss else tooth.setPos(offset, -1.26, -0.04) if is_brute else tooth.setPos(offset, -1.06, -0.06)
            tooth.setColor(0.95, 0.9, 0.78, 1.0)

        tongue = self.loader.loadModel("models/misc/sphere")
        tongue.reparentTo(root)
        tongue.setScale(0.68, 2.0, 0.16) if is_boss else tongue.setScale(0.2, 0.62, 0.06) if is_brute else tongue.setScale(0.12, 0.42, 0.06)
        tongue.setPos(0, -6.05, -0.94) if is_boss else tongue.setPos(0, -1.78, -0.28) if is_brute else tongue.setPos(0, -1.45, -0.22)
        tongue.setColor(0.95, 0.12, 0.28, 1.0)

        tentacle_model = self.loader.loadModel("models/misc/sphere")
        tentacle_offsets = (-4.5, -2.25, 0.0, 2.25, 4.5) if is_boss else (-1.15, -0.38, 0.38, 1.15) if is_brute else (-0.95, -0.32, 0.32, 0.95)
        segment_count = 7 if is_boss else 5 if is_brute else 4
        segment_scale = (0.28, 0.28, 0.95) if is_boss else (0.18, 0.18, 0.48) if is_brute else (0.14, 0.14, 0.4)
        base_z = -4.2 if is_boss else -1.35 if is_brute else -1.2
        for tentacle_index, offset in enumerate(tentacle_offsets):
            for segment_index in range(segment_count):
                segment = tentacle_model.copyTo(root)
                segment.setScale(*segment_scale)
                wave = math.sin(segment_index * 0.95 + tentacle_index * 0.7) * (0.7 if is_boss else 0.24)
                segment.setPos(
                    offset + wave,
                    -0.25 - segment_index * (0.34 if is_boss else 0.16),
                    base_z - segment_index * (0.9 if is_boss else 0.42),
                )
                segment.setColor(color[0] * 0.75, color[1] * 0.75, color[2] * 0.75, 1.0)

        if is_boss:
            crown_model = self.loader.loadModel("models/misc/sphere")
            for angle in (45, -45):
                for crown_step in range(4):
                    crown = crown_model.copyTo(root)
                    crown.setScale(0.24, 0.24, 0.7)
                    crown.setPos(
                        (-1.0 if angle < 0 else 1.0) * crown_step * 0.62,
                        -3.1,
                        2.7 - crown_step * 0.12,
                    )
                    crown.setHpr(0, 0, angle)
                    crown.setColor(0.92, 1.0, 0.75, 1.0)

    def spawn_power_bubble(self, kind: str, position: Vec3 | None = None) -> None:
        node = self.powerup_root.attachNewNode(f"power-{kind}")
        bubble = self.loader.loadModel("models/misc/sphere")
        bubble.reparentTo(node)
        bubble.setScale(1.45)
        bubble.setColor(0.55, 0.9, 1.0, 0.18)
        bubble.setTransparency(TransparencyAttrib.MAlpha)
        bubble.setLightOff()

        core = self.loader.loadModel("models/misc/sphere")
        core.reparentTo(node)
        core.setScale(0.42)
        if kind == "missile":
            core.setColor(1.0, 0.55, 0.25, 1.0)
        elif kind == "bubble":
            core.setColor(0.4, 0.95, 1.0, 1.0)
        else:
            core.setColor(0.5, 1.0, 0.65, 1.0)
        core.setLightOff()

        if kind == "missile":
            body = self.loader.loadModel("models/misc/sphere")
            body.reparentTo(node)
            body.setScale(0.12, 0.5, 0.12)
            body.setColor(1.0, 0.8, 0.3, 1.0)
            body.setPos(0, 0, -0.05)
        elif kind == "bubble":
            ring = self.loader.loadModel("models/misc/sphere")
            ring.reparentTo(node)
            ring.setScale(0.7, 0.18, 0.7)
            ring.setColor(0.2, 0.8, 1.0, 0.85)
            ring.setTransparency(TransparencyAttrib.MAlpha)
        else:
            shard = self.loader.loadModel("models/misc/sphere")
            shard.reparentTo(node)
            shard.setScale(0.18, 0.18, 0.55)
            shard.setColor(0.6, 1.0, 0.8, 1.0)

        if position is None:
            node.setPos(
                random.uniform(-22.0, 22.0),
                random.uniform(90.0, 135.0),
                random.uniform(-14.0, 14.0),
            )
        else:
            node.setPos(position + Vec3(random.uniform(-3.0, 3.0), 0.0, random.uniform(-2.0, 2.0)))

        self.power_bubbles.append(PowerBubble(root=node, kind=kind, ttl=18.0))

    def fire_primary(self) -> None:
        if self.game_over or self.cooldown_left > 0.0:
            return

        self.cooldown_left = self.fire_cooldown
        self._play_sound("laser")
        self._spawn_muzzle_line()

        if self.latched_mouths:
            mouth = self.latched_mouths.pop(0)
            pos = self.camera.getPos(self.render) + self.camera.getQuat(self.render).getForward() * 5.0
            mouth.root.removeNode()
            self._spawn_burst(pos, (1.0, 0.65, 0.25, 1.0), 0.18)
            self.message_text.setText("Parasite blasted off")
            return

        target_type, target = self._find_hitscan_target()
        if target_type == "power" and isinstance(target, PowerBubble):
            self._collect_power_bubble(target)
            return

        if target_type == "alien" and isinstance(target, Alien):
            target.hp -= 1
            self._spawn_burst(target.root.getPos(self.render), (1.0, 0.55, 0.2, 1.0), 0.16)
            if target.hp <= 0:
                self._destroy_alien(target, killed_by_bomb=False)
            elif target.kind == "boss":
                self.boss_text.setText(f"Overmind Hull: {target.hp}")

    def fire_missile(self) -> None:
        if self.game_over or self.cooldown_left > 0.0 or self.missiles <= 0:
            return

        self.missiles -= 1
        self.cooldown_left = 0.3
        self._play_sound("missile")
        target = self._find_alien_target()
        direction = self.camera.getQuat(self.render).getForward()
        origin = self.camera.getPos(self.render) + direction * 2.0
        self._spawn_player_projectile(origin, direction * 45.0, "missile", damage=5, radius=1.0, ttl=5.0, target=target)
        self.message_text.setText("Missile away")
        self._refresh_ui()

    def fire_bubble_gun(self) -> None:
        if self.game_over or self.cooldown_left > 0.0 or self.bubble_ammo <= 0:
            return

        self.bubble_ammo -= 1
        self.cooldown_left = 0.24
        direction = self.camera.getQuat(self.render).getForward()
        origin = self.camera.getPos(self.render) + direction * 1.8
        self._spawn_player_projectile(origin, direction * 28.0, "bubble_shot", damage=3, radius=1.2, ttl=3.5)
        self.message_text.setText("Bubble gun fired")
        self._refresh_ui()

    def launch_bomb(self) -> None:
        if self.game_over or self.bombs <= 0:
            return

        self.bombs -= 1
        self.bomb_flash_timer = 0.28
        cleared_latched = self._clear_latched_mouths()
        self.message_text.setText(
            "Nova bomb detonated. Hull cleared."
            if cleared_latched
            else "Nova bomb detonated"
        )
        self._spawn_shockwave()

        survivors: list[Alien] = []
        for alien in self.aliens:
            if alien.kind == "boss":
                alien.hp = max(0, alien.hp - 8)
                self._spawn_burst(alien.root.getPos(self.render), (0.75, 0.95, 1.0, 1.0), 0.28)
                if alien.hp <= 0:
                    self._destroy_alien(alien, killed_by_bomb=True, preserve_list=True)
                else:
                    survivors.append(alien)
                    self.boss_text.setText(f"Overmind Hull: {alien.hp}")
            else:
                pos = alien.root.getPos(self.render)
                self._spawn_burst(alien.root.getPos(self.render), (0.75, 0.95, 1.0, 1.0), 0.22)
                alien.root.removeNode()
                self.score += 1
                self.kills_this_level += 1
                self._maybe_spawn_power_bubble(pos)

        self.aliens = survivors
        for projectile in list(self.projectiles):
            if projectile.source == "enemy":
                projectile.root.removeNode()
                self.projectiles.remove(projectile)
        self._refresh_ui()
        self._check_stage_progress()

    def toggle_shield(self) -> None:
        if self.game_over:
            return

        if self.shield_active:
            self.shield_active = False
            self.message_text.setText("Shield lowered")
        elif self.shield_energy > 8.0:
            self.shield_active = True
            self.shield_purge_progress = 0.0
            self.message_text.setText("Shield raised")
        else:
            self.message_text.setText("Shield too weak")

    def _spawn_player_projectile(
        self,
        origin: Vec3,
        velocity: Vec3,
        kind: str,
        damage: int,
        radius: float,
        ttl: float,
        target: Alien | None = None,
    ) -> None:
        node = self.projectiles_root.attachNewNode(kind)
        mesh = self.loader.loadModel("models/misc/sphere")
        mesh.reparentTo(node)
        if kind == "missile":
            mesh.setScale(0.22, 0.56, 0.22)
            mesh.setColor(1.0, 0.72, 0.25, 1.0)
        else:
            mesh.setScale(0.4)
            mesh.setColor(0.35, 0.92, 1.0, 0.55)
            mesh.setTransparency(TransparencyAttrib.MAlpha)
        node.setPos(origin)
        node.setLightOff()
        self.projectiles.append(
            Projectile(
                root=node,
                velocity=velocity,
                radius=radius,
                damage=damage,
                ttl=ttl,
                kind=kind,
                source="player",
                target=target,
            )
        )

    def _spawn_enemy_mouth(self, alien: Alien) -> None:
        origin = alien.root.getPos(self.render) + alien.root.getQuat(self.render).getForward() * -alien.radius * 0.75
        direction = (self.camera.getPos(self.render) - origin).normalized()
        node = self.projectiles_root.attachNewNode("mouth")
        self._build_mouth_projectile(node, alien.kind == "boss")
        node.setPos(origin)
        speed = 25.0 if alien.kind == "boss" else 18.0
        damage = 2 if alien.kind == "boss" else 1
        self.projectiles.append(
            Projectile(
                root=node,
                velocity=direction * speed,
                radius=1.0 if alien.kind == "boss" else 0.7,
                damage=damage,
                ttl=5.0,
                kind="mouth",
                source="enemy",
            )
        )

    def _build_mouth_projectile(self, root: NodePath, is_boss: bool) -> None:
        mouth = self.loader.loadModel("models/misc/sphere")
        mouth.reparentTo(root)
        mouth.setScale(1.0, 0.7, 0.55) if is_boss else mouth.setScale(0.55, 0.38, 0.28)
        mouth.setColor(0.12, 0.02, 0.02, 1.0)

        teeth = self.loader.loadModel("models/misc/sphere")
        offsets = (-0.42, -0.14, 0.14, 0.42) if is_boss else (-0.12, 0.0, 0.12)
        for offset in offsets:
            tooth = teeth.copyTo(root)
            tooth.setScale(0.08, 0.08, 0.22) if is_boss else tooth.setScale(0.03, 0.03, 0.09)
            tooth.setPos(offset, -0.1, 0.1)
            tooth.setColor(1.0, 0.95, 0.8, 1.0)

        tongue = self.loader.loadModel("models/misc/sphere")
        tongue.reparentTo(root)
        tongue.setScale(0.18, 0.52, 0.05) if is_boss else tongue.setScale(0.08, 0.24, 0.03)
        tongue.setPos(0, -0.42, -0.08) if is_boss else tongue.setPos(0, -0.18, -0.04)
        tongue.setColor(1.0, 0.15, 0.28, 1.0)

    def _find_hitscan_target(self) -> tuple[str | None, object | None]:
        forward = self.camera.getQuat(self.render).getForward()
        best_type: str | None = None
        best_object: object | None = None
        best_distance = float("inf")
        best_miss = float("inf")

        def consider(obj: object, position: Vec3, radius: float, label: str, threshold: float) -> None:
            nonlocal best_type, best_object, best_distance, best_miss
            to_target = position - self.camera.getPos(self.render)
            distance = to_target.length()
            if distance <= 0.001:
                return
            direction = to_target / distance
            if forward.dot(direction) < threshold:
                return
            miss_distance = forward.cross(direction).length() * distance
            if miss_distance <= radius and distance < best_distance:
                best_type = label
                best_object = obj
                best_distance = distance
                best_miss = miss_distance
            elif miss_distance < best_miss and distance < best_distance * 1.08:
                best_type = label
                best_object = obj
                best_distance = distance
                best_miss = miss_distance

        for bubble in self.power_bubbles:
            consider(bubble, bubble.root.getPos(self.render), bubble.radius, "power", 0.93)

        for alien in self.aliens:
            threshold = 0.9 if alien.kind == "boss" else 0.94
            consider(alien, alien.root.getPos(self.render), alien.radius * (1.55 if alien.kind == "boss" else 1.0), "alien", threshold)

        return best_type, best_object

    def _find_alien_target(self) -> Alien | None:
        target_type, target = self._find_hitscan_target()
        if target_type == "alien" and isinstance(target, Alien):
            return target
        return self.boss if self.boss is not None else (self.aliens[0] if self.aliens else None)

    def _collect_power_bubble(self, bubble: PowerBubble) -> None:
        if bubble not in self.power_bubbles:
            return

        pos = bubble.root.getPos(self.render)
        bubble.root.removeNode()
        self.power_bubbles.remove(bubble)
        self._spawn_burst(pos, (0.65, 0.96, 1.0, 1.0), 0.22)

        if bubble.kind == "missile":
            self.missiles += 4
            self.message_text.setText("Missiles loaded")
        elif bubble.kind == "bubble":
            self.bubble_ammo += 10
            self.message_text.setText("Bubble gun charged")
        else:
            self.shield_energy = min(100.0, self.shield_energy + 30.0)
            self.message_text.setText("Shield cell collected")

        self._refresh_ui()

    def _destroy_alien(
        self,
        alien: Alien,
        *,
        killed_by_bomb: bool,
        preserve_list: bool = False,
    ) -> None:
        pos = alien.root.getPos(self.render)
        if not preserve_list and alien in self.aliens:
            self.aliens.remove(alien)
        alien.root.removeNode()

        if alien.kind == "boss":
            self.score += 25
            self.boss = None
            self.boss_text.setText("")
            self.message_text.setText("Boss destroyed. Planet secured.")
            self.stage = "victory"
            self.game_over = True
        else:
            self.score += 1
            self.kills_this_level += 1
            self._maybe_spawn_power_bubble(pos)

        burst_color = (0.75, 0.95, 1.0, 1.0) if killed_by_bomb else (1.0, 0.55, 0.2, 1.0)
        burst_ttl = 0.28 if killed_by_bomb else 0.18
        self._spawn_burst(pos, burst_color, burst_ttl)
        self._refresh_ui()
        self._check_stage_progress()

    def _maybe_spawn_power_bubble(self, position: Vec3) -> None:
        if random.random() > 0.34:
            return

        roll = random.random()
        kind = "missile" if roll < 0.42 else "bubble" if roll < 0.84 else "shield"
        self.spawn_power_bubble(kind, position)

    def _spawn_burst(self, position: Vec3, color: tuple[float, float, float, float], ttl: float) -> None:
        sphere = self.loader.loadModel("models/misc/sphere")
        burst = sphere.copyTo(self.effects_root)
        burst.setPos(position)
        burst.setScale(0.55)
        burst.setColor(*color)
        burst.setTransparency(TransparencyAttrib.MAlpha)
        burst.setLightOff()
        burst.setTag("ttl", f"{ttl:.2f}")
        burst.setTag("effect_type", "burst")
        self.effects.append(burst)

    def _spawn_muzzle_line(self) -> None:
        lines = LineSegs("laser")
        lines.setThickness(3.0)
        lines.setColor(0.25, 0.95, 1.0, 1.0)
        lines.moveTo(0, 1.1, -0.15)
        lines.drawTo(0, 24.0, -0.15)
        node = self.camera.attachNewNode(lines.create())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setTag("ttl", "0.05")
        node.setTag("effect_type", "laser")
        self.effects.append(node)

    def _spawn_shockwave(self) -> None:
        lines = LineSegs("shockwave")
        lines.setThickness(3.0)
        lines.setColor(0.72, 0.95, 1.0, 0.95)
        radius = 0.06
        steps = 28
        for step in range(steps):
            a0 = (math.pi * 2.0 * step) / steps
            a1 = (math.pi * 2.0 * (step + 1)) / steps
            lines.moveTo(math.cos(a0) * radius, 0, math.sin(a0) * radius)
            lines.drawTo(math.cos(a1) * radius, 0, math.sin(a1) * radius)
        node = self.aspect2d.attachNewNode(lines.create())
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", 29)
        node.setDepthTest(False)
        node.setDepthWrite(False)
        node.setTag("ttl", "0.22")
        node.setTag("effect_type", "shockwave")
        self.effects.append(node)

    def _attach_mouth(self, damage: int) -> None:
        root = self.camera.attachNewNode("latched-mouth")
        root.setPos(random.uniform(-0.45, 0.45), 2.5, random.uniform(-0.35, 0.35))
        self._build_mouth_projectile(root, is_boss=damage > 1)
        root.setScale(0.35 if damage > 1 else 0.25)
        self.latched_mouths.append(LatchedMouth(root=root, damage_timer=0.7))
        self.message_text.setText("Parasite latched on. Raise shield.")

    def _damage_player(self, amount: int = 1) -> None:
        if self.shield_active and self.shield_energy > 0.0:
            self.shield_energy = max(0.0, self.shield_energy - amount * 16.0)
            self.shield_regen_delay = 1.6
            self.flash_timer = 0.08
            if self.shield_energy <= 0.0:
                self.shield_active = False
                self.message_text.setText("Shield collapsed")
            self._refresh_ui()
            return

        self.health -= amount
        self._play_sound("human_hit")
        self.flash_timer = 0.18
        if self.health <= 0:
            self.health = 0
            self.game_over = True
            self.message_text.setText("Hull breach. Press R to restart")
            self.boss_text.setText("")
            self.game_over_text.setText("HULL BREACH")
        self._refresh_ui()

    def _heal_hull_from_shield(self, shield_spent: float) -> None:
        if shield_spent <= 0.0 or self.health >= self.max_health:
            return
        self.health = min(self.max_health, self.health + (shield_spent / 20.0))

    def _refresh_ui(self) -> None:
        self.score_text.setText(f"Score: {self.score}")
        displayed_hull = int(math.ceil(self.health)) if self.health > 0 else 0
        self.health_text.setText(f"Hull: {displayed_hull}/{int(self.max_health)}")
        self.shield_text.setText(f"Shield: {int(self.shield_energy)}%{' ON' if self.shield_active else ''}")
        self.ammo_text.setText(f"Bombs: {self.bombs}  Missiles: {self.missiles}  Bubbles: {self.bubble_ammo}")
        attached_count = len(self.latched_mouths)
        self.attached_text.setText(f"Attached: {attached_count}")
        self.attached_text.setFg((1.0, 0.35, 0.35, 1.0 if attached_count else 0.25))
        self.attached_overlay.setColor(1.0, 0.32, 0.32, min(0.85, attached_count * 0.16))
        if not self.game_over or self.health > 0:
            self.game_over_text.setText("")

        if self.stage == "assault":
            self.stage_text.setText("Sector: Alien Front")
        elif self.stage == "approach":
            self.stage_text.setText("Vector: Planetfall")
        elif self.stage == "boss":
            self.stage_text.setText("Threat: Alien Overmind")
        elif self.stage == "victory":
            self.stage_text.setText("Status: Planet Secured")

        self.progress_bar.setSx(max(0.05, self._mission_progress()))
        self._update_nav_text()

    def _mission_progress(self) -> float:
        if self.stage == "assault":
            return min(1.0, self.kills_this_level / self.assault_target)
        if self.stage == "approach":
            distance = self.planet.getY() - self.planet_target_y
            total = 420.0 - self.planet_target_y
            return min(1.0, max(0.0, 1.0 - (distance / total)))
        if self.stage == "boss" and self.boss is not None:
            return min(1.0, max(0.0, 1.0 - (self.boss.hp / 38.0)))
        return 1.0

    def _update_nav_text(self) -> None:
        if self.stage == "assault":
            remaining = max(0, self.assault_target - self.kills_this_level)
            self.nav_text.setText(f"NAV: Clear {remaining} hostiles")
            return

        if not self.planet.isHidden():
            cam_point = self.camera.getRelativePoint(self.render, self.planet.getPos(self.render))
            directions: list[str] = []
            if cam_point.x > 12.0:
                directions.append("RIGHT")
            elif cam_point.x < -12.0:
                directions.append("LEFT")
            if cam_point.z > 10.0:
                directions.append("UP")
            elif cam_point.z < -10.0:
                directions.append("DOWN")
            if not directions:
                directions.append("LOCKED")
            distance = int((self.planet.getPos(self.render) - self.camera.getPos(self.render)).length())
            self.nav_text.setText(f"NAV: {' '.join(directions)}  {distance} km")
        else:
            self.nav_text.setText("NAV: Sweep for hostiles")

    def _check_stage_progress(self) -> None:
        if self.stage == "assault" and self.kills_this_level >= self.assault_target:
            self.stage = "approach"
            self.message_text.setText("Alien line broken. Follow the nav marker.")
            self.planet.show()
            self.spawn_timer = 0.0
            self._refresh_ui()

        if self.stage == "boss" and self.boss is None and not self.game_over:
            self.stage = "victory"
            self.game_over = True
            self.message_text.setText("Boss destroyed. Press R to fly again.")
            self._refresh_ui()

    def _update_camera(self, dt: float) -> None:
        if not self.mouseWatcherNode.hasMouse():
            return

        pointer = self.win.getPointer(0)
        dx = pointer.getX() - self.center_x
        dy = pointer.getY() - self.center_y
        if dx == 0 and dy == 0:
            return

        heading = self.camera.getH() - dx * self.turn_speed * dt
        pitch = self.camera.getP() - dy * self.pitch_speed * dt
        pitch = max(-55.0, min(55.0, pitch))
        self.camera.setHpr(heading, pitch, 0)
        self.win.movePointer(0, self.center_x, self.center_y)

    def _update_stars(self, dt: float) -> None:
        speed_boost = 1.55 if self.stage == "approach" else 1.0
        for star in self.stars:
            pos = star.node.getPos()
            pos.y -= star.speed * self.star_speed * 0.02 * dt * speed_boost
            if pos.y < -60.0:
                self._reset_star(star.node)
            else:
                star.node.setPos(pos)

    def _update_planet(self, dt: float) -> None:
        if self.stage != "approach":
            return

        self.planet.show()
        self.planet.setY(max(self.planet_target_y, self.planet.getY() - self.approach_speed * dt))
        self.planet.setH(self.planet.getH() + 4.0 * dt)
        self.planet.setP(self.planet.getP() + 1.8 * dt)

        if self.planet.getY() <= self.planet_target_y and not self.boss_spawned:
            self.stage = "boss"
            self.message_text.setText("Alien Overmind incoming")
            self.spawn_alien("boss")
            self._refresh_ui()

    def _update_shield(self, dt: float) -> None:
        if self.shield_active:
            previous_energy = self.shield_energy
            self.shield_energy = max(0.0, self.shield_energy - 26.0 * dt)
            self.shield_regen_delay = 1.5
            self.shield_card.setColor(0.2, 0.8, 1.0, 0.14 + math.sin(globalClock.getFrameTime() * 8.0) * 0.02)
            if self.shield_energy <= 0.0:
                self.shield_active = False
                self.message_text.setText("Shield collapsed")

            if self.latched_mouths:
                self.shield_purge_progress += previous_energy - self.shield_energy
                detach_count = min(len(self.latched_mouths), int(self.shield_purge_progress / 10.0))
                if detach_count > 0:
                    for _ in range(detach_count):
                        mouth = self.latched_mouths.pop(0)
                        mouth.root.removeNode()
                        self.shield_purge_progress -= 10.0
                    self.message_text.setText("Shield burned off parasites")
            else:
                self._heal_hull_from_shield(previous_energy - self.shield_energy)
        else:
            self.shield_card.setColor(0.2, 0.8, 1.0, 0.0)
            if self.shield_regen_delay > 0.0:
                self.shield_regen_delay = max(0.0, self.shield_regen_delay - dt)
            else:
                self.shield_energy = min(100.0, self.shield_energy + 12.0 * dt)

    def _update_power_bubbles(self, dt: float) -> None:
        remaining: list[PowerBubble] = []
        t = globalClock.getFrameTime()
        for bubble in self.power_bubbles:
            bubble.ttl -= dt
            if bubble.ttl <= 0.0:
                bubble.root.removeNode()
                continue

            pos = bubble.root.getPos()
            pos.y -= 7.0 * dt
            pos.z += math.sin(t * 1.8 + pos.x * 0.1) * 0.22 * dt
            bubble.root.setPos(pos)
            bubble.root.setH(bubble.root.getH() + 26.0 * dt)
            remaining.append(bubble)
        self.power_bubbles = remaining

    def _update_projectiles(self, dt: float) -> None:
        remaining: list[Projectile] = []
        for projectile in self.projectiles:
            projectile.ttl -= dt
            if projectile.ttl <= 0.0:
                projectile.root.removeNode()
                continue

            if projectile.kind == "missile" and projectile.target is not None and projectile.target in self.aliens:
                desired = (projectile.target.root.getPos(self.render) - projectile.root.getPos(self.render)).normalized()
                current = projectile.velocity.normalized()
                steer = (current * 0.78 + desired * 0.22).normalized()
                projectile.velocity = steer * projectile.velocity.length()
                projectile.root.lookAt(projectile.target.root)

            projectile.root.setPos(projectile.root.getPos() + projectile.velocity * dt)

            if projectile.source == "enemy":
                distance = projectile.root.getPos(self.render).length()
                if distance <= 2.0:
                    if self.shield_active and self.shield_energy > 0.0:
                        self._spawn_burst(projectile.root.getPos(self.render), (0.4, 0.9, 1.0, 1.0), 0.16)
                        self._damage_player(1)
                    else:
                        self._attach_mouth(projectile.damage)
                    projectile.root.removeNode()
                    continue
            else:
                hit_handled = False
                for bubble in list(self.power_bubbles):
                    if (bubble.root.getPos(self.render) - projectile.root.getPos(self.render)).length() <= bubble.radius:
                        self._collect_power_bubble(bubble)
                        projectile.root.removeNode()
                        hit_handled = True
                        break
                if hit_handled:
                    continue

                for alien in list(self.aliens):
                    if (alien.root.getPos(self.render) - projectile.root.getPos(self.render)).length() <= alien.radius + projectile.radius:
                        alien.hp -= projectile.damage
                        burst_color = (0.45, 0.95, 1.0, 1.0) if projectile.kind == "bubble_shot" else (1.0, 0.68, 0.28, 1.0)
                        self._spawn_burst(projectile.root.getPos(self.render), burst_color, 0.2)
                        if alien.hp <= 0:
                            self._destroy_alien(alien, killed_by_bomb=False)
                        elif alien.kind == "boss":
                            self.boss_text.setText(f"Overmind Hull: {alien.hp}")
                        projectile.root.removeNode()
                        hit_handled = True
                        break
                if hit_handled:
                    continue

            remaining.append(projectile)

        self.projectiles = remaining

    def _update_latched_mouths(self, dt: float) -> None:
        for mouth in list(self.latched_mouths):
            mouth.damage_timer -= dt
            mouth.root.setR(mouth.root.getR() + 55.0 * dt)
            if mouth.damage_timer <= 0.0:
                mouth.damage_timer = 0.8
                self._damage_player(1)
                self.message_text.setText("They are eating through the hull")

    def _update_boss(self, dt: float) -> None:
        if self.boss is None or self.game_over:
            return

        pos = self.boss.root.getPos()
        t = globalClock.getFrameTime()
        pos.x = math.sin(t * 0.9) * 24.0
        pos.z = 8.0 + math.sin(t * 1.4) * 7.0
        pos.y = max(54.0, pos.y - 1.5 * dt)
        self.boss.root.setPos(pos)
        self.boss.root.lookAt(self.camera)
        self.boss.root.setR(math.sin(t * 1.8) * 5.0)

        self.add_spawn_timer += dt
        if self.add_spawn_timer >= 4.6:
            self.add_spawn_timer = 0.0
            self.spawn_alien("escort")

        if pos.length() <= 10.0:
            self._spawn_burst(pos, (1.0, 0.2, 0.2, 0.9), 0.28)
            self._damage_player(2)
            self.boss.root.setY(110.0)

    def _update_aliens(self, dt: float) -> None:
        hit_list: list[Alien] = []
        for alien in list(self.aliens):
            alien.attack_cooldown -= dt

            if alien.kind == "boss":
                if alien.attack_cooldown <= 0.0:
                    alien.attack_cooldown = 1.1
                    self._spawn_enemy_mouth(alien)
                continue

            alien.root.lookAt(self.camera)
            wobble = math.sin(globalClock.getFrameTime() * 4.0 + alien.root.getX()) * 0.6
            alien.root.setR(wobble * 7.0)

            if self.stage == "boss" and alien.kind == "escort":
                drift = math.sin(globalClock.getFrameTime() * 2.0 + alien.root.getZ()) * 2.0
                alien.root.setX(alien.root.getX() + drift * dt)

            alien.root.setPos(alien.root.getPos() + alien.velocity * dt)

            if alien.attack_cooldown <= 0.0 and alien.root.getY() < 70.0:
                alien.attack_cooldown = 2.2 if alien.kind == "escort" else 2.8
                self._spawn_enemy_mouth(alien)

            if alien.root.getPos().length() <= 2.1:
                hit_list.append(alien)

        for alien in hit_list:
            if alien in self.aliens:
                pos = alien.root.getPos(self.render)
                self.aliens.remove(alien)
                alien.root.removeNode()
                self._spawn_burst(pos, (1.0, 0.2, 0.2, 0.9), 0.2)
                if self.shield_active and self.shield_energy > 0.0:
                    self._damage_player(1)
                else:
                    self._attach_mouth(1)

    def _update_effects(self, dt: float) -> None:
        remaining: list[NodePath] = []
        for effect in self.effects:
            ttl = float(effect.getTag("ttl")) - dt
            if ttl <= 0.0:
                effect.removeNode()
                continue

            effect.setTag("ttl", f"{ttl:.4f}")
            effect_type = effect.getTag("effect_type")

            if effect_type == "laser":
                alpha = ttl / 0.05
                color = effect.getColor()
                effect.setColor(color[0], color[1], color[2], max(0.0, alpha))
            elif effect_type == "shockwave":
                alpha = ttl / 0.22
                scale = 1.0 + (0.22 - ttl) * 8.0
                effect.setScale(scale)
                color = effect.getColor()
                effect.setColor(color[0], color[1], color[2], max(0.0, alpha))
            else:
                alpha = min(1.0, ttl / 0.28)
                color = effect.getColor()
                effect.setColor(color[0], color[1], color[2], max(0.0, alpha))
                effect.setScale(effect.getScale() + Vec3(dt * 6.0))

            remaining.append(effect)
        self.effects = remaining

    def update(self, task: Task) -> int:
        dt = min(globalClock.getDt(), 1.0 / 20.0)

        if self.win.getXSize() > 0 and self.win.getYSize() > 0:
            self.center_x = self.win.getXSize() // 2
            self.center_y = self.win.getYSize() // 2

        if self.cooldown_left > 0.0:
            self.cooldown_left = max(0.0, self.cooldown_left - dt)

        if self.flash_timer > 0.0:
            self.flash_timer = max(0.0, self.flash_timer - dt)
        if self.bomb_flash_timer > 0.0:
            self.bomb_flash_timer = max(0.0, self.bomb_flash_timer - dt)

        self.flash_card.setColor(1.0, 0.2, 0.2, min(0.35, self.flash_timer * 2.0))
        self.bomb_flash_card.setColor(0.7, 0.95, 1.0, min(0.32, self.bomb_flash_timer * 1.8))
        self.game_over_card.setColor(0.02, 0.02, 0.05, 0.58 if self.game_over and self.health <= 0 else 0.0)

        self._update_camera(dt)
        self._update_shield(dt)
        self._update_stars(dt)
        self._update_planet(dt)
        self._update_power_bubbles(dt)
        self._update_projectiles(dt)
        self._update_effects(dt)
        self._update_latched_mouths(dt)

        if self.game_over:
            self._refresh_ui()
            return Task.cont

        if self.stage == "assault":
            self.spawn_timer += dt
            if self.spawn_timer >= self.spawn_interval:
                self.spawn_timer = 0.0
                self.spawn_alien("brute" if random.random() < 0.26 else "scout")
                self.spawn_interval = max(0.5, self.spawn_interval * 0.992)
                self.alien_speed = min(17.0, self.alien_speed + 0.05)
        elif self.stage == "approach":
            self.spawn_timer += dt
            if self.spawn_timer >= 2.2:
                self.spawn_timer = 0.0
                self.spawn_alien("brute" if random.random() < 0.35 else "escort")
            self.powerup_spawn_timer += dt
            if self.powerup_spawn_timer >= 6.0:
                self.powerup_spawn_timer = 0.0
                self.spawn_power_bubble(random.choice(["missile", "bubble", "shield"]))
        elif self.stage == "boss":
            self._update_boss(dt)
            self.powerup_spawn_timer += dt
            if self.powerup_spawn_timer >= 8.0:
                self.powerup_spawn_timer = 0.0
                self.spawn_power_bubble(random.choice(["missile", "bubble", "shield"]))

        self._update_aliens(dt)
        self._refresh_ui()
        return Task.cont


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hyper Jump")
    parser.add_argument("--smoke-report", type=Path,
                        help="Run the packaged native smoke test and write its JSON result")
    args = parser.parse_args()
    if args.smoke_report:
        # Real software-rendered window, without requiring a hosted runner GPU
        # or audio device. This configuration is never used for normal play.
        loadPrcFileData("smoke", "win-size 640 480\nsync-video 0\naudio-library-name null\nload-display p3tinydisplay")
    game = AlienShooterGame()
    if args.smoke_report:
        from native_smoke import run
        try:
            run(game, args.smoke_report)
        finally:
            game.destroy()
    else:
        game.run()
