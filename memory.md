# Project memory

This file records stable local facts needed for later work on the BBM compatibility project. Do not put passwords, access tokens, signing secrets, or private keys here.

## Workspace and source

- Workspace: `D:\VSC\Big bad monster`
- Target package: `net.commseed.bbm`, Android 1.4.1 / versionCode 43, Unity 2018.4.17f1, IL2CPP 24.1.
- User-supplied XAPK, extracted APK/OBB, reverse-engineering output, generated APKs, runtime data, tools, virtualenv, TLS files and signing keystore are local-only and covered by `.gitignore`.
- Never commit or upload `input/`, `analysis/`, `output/`, `.local/`, `.tools/`, `.venv/`, or `runtime/`.

## MuMu emulator

- Correct ADB path: `D:\Program Files\Netease\MuMu\nx_main\adb.exe`
- MuMu CLI: `D:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe`
- The originally suggested `D:\Program Files\Netease\MuMu\nx\_main\adb.exe` does not exist on this machine.
- Known player: VM index `1`, name `MuMu安卓设备`, Android 15. It was stopped when last inspected on 2026-09-05.
- Launch command: `& 'D:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe' control --vmindex 1 launch`
- Device check: `& 'D:\Program Files\Netease\MuMu\nx_main\adb.exe' devices -l`

## Current compatibility milestone

- Local server origin and patched client origin: `https://192.168.0.243:9100`.
- Server binds `0.0.0.0:9100`; the client must never be patched to `0.0.0.0`.
- Generated client: `output\client-lan-9100\signed\bbm-local-aligned-debugSigned.apk` (local-only, ignored by Git).
- OBB: `analysis\xapk_1.4.1\Android\obb\net.commseed.bbm\main.43.net.commseed.bbm.obb` (local-only, ignored by Git).
- Implemented: bootstrap, local device login, token login, sessions, user/profile/wallet/equip/monster/town/store read chain, selected auxiliary reads, exact asset allowlist.
- Not implemented: tutorial mutations, city mutations, progression, purchases, battles, chat and real multiplayer.
- Verification status: 18 unit/integration tests pass and the running HTTPS synthetic probe passes. No emulator/device end-to-end result yet.

## Operational notes

- Start server: `.\start-server.ps1`
- Test: `.venv\Scripts\python.exe -m unittest discover -s tests -v`
- Probe: `.venv\Scripts\python.exe -m tools.probe`
- Player admin: `.venv\Scripts\python.exe -m tools.manage_player list`
- Initial new-account economy/content: `config\gameplay.json`; existing wallets live in ignored SQLite state.
- If the host IP changes, regenerate both `.local/server.json` and the client APK using the same HTTPS origin.
- The compatibility server intentionally permits device-UDID login for this client build and must remain LAN/private-test only.
