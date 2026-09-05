# Big Bad Monsters 1.4.1 — initial client analysis

## Source artifact

- Package: `input/【配信終了】ビッグバッドモンスターズ_1.4.1.xapk`
- SHA-256: `911C38B0D51614B73EEEC2B3EC0019FFF9B5A40583363EFAF6CDE31460BCCA7D`
- XAPK package name: `net.commseed.bbm`
- Version: `1.4.1` (`versionCode` 43)
- Minimum/target SDK: 19/29

The original XAPK was not modified. Its contents were extracted under
`analysis/xapk_1.4.1/` for read-only inspection.

## Package layout

- Base APK: about 75 MiB
- Main OBB: about 534 MiB
- Architectures: ARMv7 and ARM64
- Engine: Unity 2018.4.17f1, using IL2CPP
- IL2CPP metadata version: 24.1 (header reports 24)
- Relevant files:
  - `apk/assets/bin/Data/Managed/Metadata/global-metadata.dat`
  - `apk/lib/arm64-v8a/libil2cpp.so`
  - `apk/lib/armeabi-v7a/libil2cpp.so`
  - `obb/assets/bin/Data/`

## Network evidence

The following strings are embedded in the client:

- Production bootstrap/version service: `https://version.bigbadmonsters.net:9100`
- QA bootstrap services:
  - `https://qa-version.bigbadmonsters.net:9100`
  - `https://qa-2-version.bigbadmonsters.net:9100`
- Historical test addresses:
  - `http://103.114.126.10:9100`
  - `http://10.99.0.101:9100`
  - `http://10.99.0.235:9100`
  - `http://10.99.1.1:9100`
- A second observed port: `9110`
- Firebase project URL: `https://bbm-japan.firebaseio.com`

The metadata contains WebSocket protocol strings, including
`Sec-WebSocket-Key`, `Sec-WebSocket-Version`, and a `wss://...transport=...`
format. It also contains acknowledgement logging in the form
`[Ack: packetId={0}, time={1}, action={2}]`.

Follow-up native analysis confirms HTTP POST for the WebManager game API;
WebSocket/Socket.IO code is also present for chat. The bootstrap response
contains GameServer, BattleServer, ReportServer and bundle addresses; chat
discovery has a separate route. See `docs/protocol.md` for confirmed wire
format, DTO fields, implementation status and remaining runtime checks.

## Recovered action names

The client metadata exposes a large action surface. Representative actions:

- Bootstrap/session: `GetServerInfo`, `IsLoginAble`, `CreateUser`, `GetUserInfo`
- Town: `GetUserTownMapInfo`, `TxMoveUserProp`, `TxFinishUserProp`,
  `TxOverwriteUserTownMapInfo`
- Monsters: `GetUserMonsterInventory`, `TxGrowMonster`, `TxEvolveMonster`,
  `TxUpdateUserMonsterDeck`
- PvP/PvE: `TxAttackPvpVillage`, `TxSetPvpGameEndData`,
  `TxAttackPveVillage`, `TxSetPveGameEndData`
- Friends: `GetUserFriendList`, `TxRequestFriend`, `TxAddUserFriend`
- Clan/chat: `GetChatServerInfo`, `GetClanInfoListByFilter`, `TxCreateClan`,
  `TxSendClanChatBoard_Chat`, `TxSendClanChatBoard_Emoticon`
- Economy: `GetUserWalletInfo`, `GetUserStoreInfoList`, `TxBuyItemStoreItem`,
  `TxValidateReceipt`

Names found next to unrelated strings in the raw metadata must be separated
using IL2CPP metadata tables before treating them as exact routes. The action
prefixes and the representative names above recur consistently enough to be
useful discovery targets.

## Recommended reconstruction order

1. Generate IL2CPP type/method metadata from `global-metadata.dat` and
   `libil2cpp.so`.
2. Locate the types that own `GetServerInfo`, WebSocket connection setup,
   packet encoding/decoding, and acknowledgement handling.
3. Recover the bootstrap request/response DTOs and message envelope.
4. Run the unmodified client in a test device/emulator and record its first
   failure without sending credentials to third parties.
5. Implement a local bootstrap/WebSocket probe server that logs the client's
   handshake and returns only controlled placeholder responses.
6. Redirect a locally patched client build to that server.
7. Implement guest login and a minimal user profile before town, inventory,
   and battle features.

## Boundaries

The reconstruction should use clean-room observations from a lawfully held
client and public gameplay material. It should not use leaked server code,
credentials, private databases, payment impersonation, or distribution of
the original copyrighted package/assets. Real-money purchase routes should
remain disabled in a private preservation server.
