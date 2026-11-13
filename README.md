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

Tom builds and tests macOS locally, then publishes its DMG (or Mac ZIP/PKG) on the matching `vMAJOR.MINOR.PATCH` GitHub release. On Sunday morning Pacific (16:17 UTC), native GitHub-hosted Linux x64 and Windows x64 runners pick up new version tags **only after that published release contains a Mac asset**. Each runner builds the exact tagged commit, packages the complete app, extracts the archive into a clean temporary location, and checks a real rendered frame plus firing, enemy spawning, shield and restart behavior. CI uses silent audio and software rendering; this is a packaging/startup/gameplay smoke test, not a full play-through, audio playback test or GPU compatibility certification.

Passing targets are attached independently to that same release as `Hyper-Jump-<tag>-linux-x64.tar.gz` or `Hyper-Jump-<tag>-windows-x64.zip`, with a `.smoke.json` receipt containing the tested archive SHA-256 and run provenance. Extract the entire archive before launching the executable inside `Hyper Jump`. Linux packages target Ubuntu 24.04-compatible x64 systems; Windows packages target x64 Windows. Neither package is code-signed by this workflow.

Existing tags stay baselined, so `v0.1.0` is not retroactively rebuilt. Missing Mac releases wait without consuming an attempt. Attempted builds, failed smoke tests, publication failures and uncertain uploads are **not automatically retried**; inspect the linked workflow and request targeted recovery explicitly. Existing assets are never overwritten. CI never creates/releases a version on Tom's behalf, moves tags, builds macOS or enables the archived macOS workflow. New tags must include the packaged smoke-test entry point introduced with this workflow. See [.github/scripts/NATIVE_RELEASE_POLICY.md](.github/scripts/NATIVE_RELEASE_POLICY.md) for the release contract.

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
