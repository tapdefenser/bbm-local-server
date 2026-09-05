# 1.4.1 login/read-model compatibility notes

This is a working implementation based on static evidence, not a claim of a working game.
No request was sent to the historical game services. Real-device integration remains outstanding.

## Sources and tool versions

- Supplied APK SHA-256: `4218e0dcccfe2fb86617588a41557edc5269ea0fae5780e03a3e31e6c3f7501e`.
- Metadata SHA-256: `77282de5193ffa9c4b3648bc5704b01d1fb7194edb9c60fd9e60a7a6d49f8cf6`.
- Unity `2018.4.17f1`, IL2CPP `24.1`, ARM64 analysis.
- [Il2CppDumper 6.7.46](https://github.com/Perfare/Il2CppDumper/releases/tag/v6.7.46): outputs in `analysis/il2cpp-arm64/`.
- Capstone 5.0.6 / pyelftools 0.32 for local native-code inspection.
- [uber-apk-signer 1.3.0](https://github.com/patrickfav/uber-apk-signer/releases/tag/v1.3.0): pinned SHA-256 in build tool. APK alignment/signatures verified. The 24 verifier warnings concern preserved AndroidX `META-INF/*.version` entries under v1 signing; v2/v3 verification also passes.

## Confirmed transport

`WebManager.<WWWPost>d__26.MoveNext`, ARM64 VA `0x4540550`, concatenates `Req_Base.HOST + URL`, constructs a Unity WWWForm, then submits via UnityWebRequest.Post.

1. `Req_VersionServer..ctor` (`0x3e7f280`) sets `IsJWT=false`.
2. For this path, form field `jsonPacket` contains the serialized request JSON.
3. For game requests (`Req_Base.IsJWT=true` by default), the client puts that JSON string inside a JWT claim also named `jsonPacket`.
4. JWT uses HS256. `exp` is included only when the client's server clock is initialized, with a 300-second lifetime.
5. JWT UTF-8 bytes are encrypted with AES-128, ECB, PKCS7, then standard Base64 encoded into form field `bbmPacket`.
6. Server responses are plain JSON response objects, not encrypted/JWT wrapped. `WebPacketWrapper.EBFHDBABCLH` at `0x42413b4` reads `DownloadHandler.text` and passes it to the response parser, which uses JsonConvert.DeserializeObject.

`WebManager.Start` (`0x1dab0d4`) copies the first 16 UTF-8 bytes of its crypto literal and configures RijndaelManaged `Key`, `Mode=2` (ECB), `Padding=2` (PKCS7), CreateEncryptor.
The static protocol material is read from the user's original package in memory (literal indices 1320 and 1345), and is not committed to implementation files.

`ServerResult.SUCCESS=1`, `FAIL=0`; treating zero as success would be incompatible.

`WebManager.GetAllPassCertHandler` (`0x1dabb0c`) creates a handler whose `ValidateCertificate` (`0x3e7d9d8`) returns true.
WWWPost attaches it for HTTPS. ResourceManager.CheckPatchList also attaches this handler for HTTPS.
The project does not modify this behavior or the system certificate store.

## Addresses

`BuildSetting..cctor` (`0x2a37dd8`) initializes:

- Major/Minor/Patch = 1/4/1;
- IncludeAssetBundleVersion = 240;
- WebConnectType = 9 (`LIVE`);
- WebEnvType = 0 (`MAIN`).

`HostResolver.PEFCBKDIKEK` (`0x3e7e37c`) selects the version-server string according to WebConnectType.
The patch rewrites production and both QA strings in the shared IL2CPP metadata, so it applies to both packaged ARM architectures.
Only those three literals and their length entries change. Other development URLs are retained and are not selected by the confirmed LIVE default.

`Res_GetServerInfo` has `serverInfo` and `maintenanceInfo`, in addition to Res_Base fields.
The exact public DTO names are:

```text
serverInfo
  AppVersion
    aos / ios: Major, Minor, Patch, SkipMarketUpdate
  Main / Review
    url: GameServer, BattleServer, ReportServer
    aos / ios: downloadUrl, BundleVersion, BundlePath
maintenanceInfo
  isOpen, messageType, jp, en, kr, stringKey, arg0, arg1, arg2, isTerminatedBBM
```

The prototype returns local origins in all three server URL fields and a `/bundles` path.
It advertises bundle version 240 to match the installed data. The included `patch_result.json` and `.bin` plus exactly the 305 declared bundle filenames can be served.
Hash correctness, all asset dependencies, bundle-path joining and actual update decisions still require runtime verification.

## Implemented routes

| Route | Behavior |
| --- | --- |
| GET `/healthz` | Local diagnostic status, explicitly reports gameplayReady=false |
| POST `/GetServerInfo` | Matching version/server DTO fields, local addresses |
| POST `/CreateUser` | Creates local `udid` and `accessToken` |
| POST `/IsLoginAble` | Checks that local UDID exists |
| POST `/LoginUser` | Verifies local UDID/token; returns `sessionInfo`, `serverTime`, `opponentName` |
| POST `/Login` | Optional LAN-only device login required by `ClientInstance.Login` / `SendDevLogin` |
| POST `/Ping` | Requires valid local user/session; echoes txId |
| POST `/GetUserInfo` | Persisted local identity and initial profile |
| POST `/GetUserWalletInfo` | Persisted wallet plus initial mode-wallet values |
| POST `/GetUserEquipInfo` | Initial deck selection and inventory capacities |
| POST `/GetUserMonsterInventory` | Initial monsters and team from the packaged development sample |
| POST `/GetUserTownMapInfo` | Minimal initial town with persisted identity/economy values |
| POST `/GetUserStoreInfoList` | Empty valid store purchase-history list |
| POST `/GetUserTutorialList` | Empty completed-tutorial list |
| POST `/GetUserShield` | No active shield |
| POST `/GetUserSummonShopInfo` | Empty summon-shop state |
| POST `/GetChatServerInfo` | Explicit `CANT_GET_CHAT_SERVER_INFO` (-5001) until chat is implemented |
| Other game routes | Explicit failure; no successful dummy mutations |

Local account IDs, names, random int64 sessions and 24-hour expiry are implementation choices, not recovered official behavior.
ARM64 `ClientInstance.Login` at `0x3799050` calls `WebManager.SendDevLogin`; after success its callback begins the fixed read chain: user info, wallet, equip, monster inventory, own town, store list.
The compatibility server therefore supports device login only when `allow_dev_login` is explicitly enabled. It is not suitable for an Internet-facing deployment.
`serverTime` uses Unix seconds, consistent with the client's exp and second-based time helper.

The starting 500 coin / 500 candy wallet and the three monsters with IDs 302, 200301, and 602 are copied from the OBB's `userWallet01` and `userMonster01` TextAssets.
They are configuration evidence, not proof that the production service used precisely that onboarding state.
No tutorial progression, town mutation, battle, purchasing or multiplayer logic is implemented yet.

## Verification

- 18 unittest cases: HTTPS bootstrap and encrypted login/read-model requests, independent .NET crypto fixture, account/session/wallet persistence, bad signatures/expiry, traversal rejection, and patch scope/source-integrity checks.
- Signed APK ZIP contents compared with original: all non-signature entries unchanged except the intended metadata patch.
- v1, v2, v3 APK signatures and ZIP alignment verified by the signer.
- Device testing pending: no connected ADB target when implemented.

The next evidence needed is the modified client's first requests/logcat and rendered initial town. Confirm the recovered request order, then implement only the first actually requested tutorial mutation and its persisted state transition.
