# Hyper Jump

A small cross-platform Python prototype for a fixed-position first-person alien shooter in 3D space.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Run the game:

```bash
python main.py
```

## Build A macOS App Bundle

1. Install the build dependency:

```bash
python -m pip install -r build_requirements.txt
```

2. Build the app bundle/executable:

```bash
env PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller" python -m PyInstaller -y "Hyper Jump.spec"
```

3. Find the built `.app` bundle in `dist/Hyper Jump.app`.

## Build A macOS DMG

After building the app bundle, create a DMG with:

```bash
scripts/build-macos-dmg.sh
```

The DMG is written to `dist/Hyper Jump-macOS-<arch>.dmg`.

## GitHub Releases

Pushing a tag like `v1.0.0` triggers the GitHub Actions workflow in `.github/workflows/release-macos.yml`, which:

1. Builds the macOS `.app`
2. Packages it into a DMG
3. Uploads the DMG to the corresponding GitHub Release

That Release asset is the recommended download location for macOS players.

## Controls

- Move mouse: look around
- Left click or `Space`: fire pulse cannon
- `F`: fire missile
- `G`: fire bubble gun
- `B`: launch bomb
- `E`: toggle shield
- `R`: restart after game over
- `Esc`: quit

## Notes

The player stays fixed in place while aliens rush in from space. Shoot floating power bubbles to collect missiles, bubble gun ammo, and shield energy. During planetfall, use the nav indicator to line up with the planet before the boss encounter.
