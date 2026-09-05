https://play.google.com/store/apps/details?id=net.commseed.bbm

# BBM 本地兼容服务器（登录与首屏原型）

针对现有 Android `net.commseed.bbm` 1.4.1 / versionCode 43。
当前实现启动查询、本地设备登录、令牌账号、会话保存，以及登录后的资料、钱包、编队、怪物库存、初始城市和商店读取链。
**尚不能承诺进入完整游戏；城市写操作、养成、战斗和聊天仍未实现。**
所有客户端兼容性结论目前来自静态分析与模拟请求，尚未完成手机/模拟器端到端验证。

## 已生成的客户端

`output/client-lan-9100/signed/bbm-local-aligned-debugSigned.apk`

启动地址为 `https://192.168.0.243:9100`。这是构建时电脑的 WLAN 地址；电脑地址改变后需要重新配置和生成 APK。
`output/client-lan-9100/patch-report.json` 记录源文件哈希、修改位置、输出哈希和验证状态。

补丁修改 IL2CPP 字符串表中生产和两个 QA 版本服务器地址，并更新字符串长度。
APK 中其余内容（包括 AndroidManifest、两种架构的原生代码）已逐项核对保持一致。
签名与 ZIP 对齐均验证通过。修改包使用本项目自己的开发签名。

## 启动服务

在本项目目录打开 PowerShell：

```powershell
# 环境已准备好时，直接运行：
.\start-server.ps1

# 第一次在其他机器使用时：
.\tools\setup.ps1
.\start-server.ps1 -ServerUrl https://你的电脑局域网IP:9100
```

`setup.ps1` 创建项目内 Python 环境并下载校验过的 APK 签名工具。
Python 3.9+ 用于服务端，JDK 的 java/keytool 用于客户端签名；服务器不要求 Unity Editor。
配置保存在 `.local/server.json`。数据库和脱敏请求日志分别是 `runtime/bbm.sqlite3`、`runtime/requests.jsonl`。
前台运行按 Ctrl+C 停止。第一次配置会生成仅供本项目使用的 TLS 证书。

`public_url` 必须是设备能访问的地址。`listen_host=0.0.0.0` 只是监听所有本地网卡，不能填到客户端中。
游戏服务器、战斗服务器和资源地址均由 `/GetServerInfo` 返回本地地址，避免启动后再连接旧域名。
聊天尚未实现，暂不返回虚假的可用聊天地址。
1.4.1 客户端的 `ClientInstance.Login` 实际调用无访问令牌的 `SendDevLogin`；本项目只在 `allow_dev_login=true` 时为设备 UDID 创建或恢复本地账号。
这是为了兼容停服客户端的局域网模式，不应把当前服务直接暴露到互联网。

## 初始数据与经济数值

新账号初始钱包、怪物、编队、容量和城市骨架在 `config/gameplay.json`。
其中 500 金币、500 糖果和三只初始怪物来自原 OBB 内置的 `userWallet01` / `userMonster01` 开发样例。
修改该文件影响此后创建的新账号；已经创建的账号钱包保存在 SQLite，不会被启动配置覆盖。

查看本地账号和钱包：

```powershell
.venv\Scripts\python.exe -m tools.manage_player list
```

修改现有 1 号账号的钱包（可只传需要改的字段）：

```powershell
.venv\Scripts\python.exe -m tools.manage_player set-wallet --user-id 1 --coin 50000 --candy 50000 --cash 1000
```

服务运行时也可以执行；下一次客户端刷新钱包即可读到持久化数值。当前购买、掉落和结算尚不会自动增减货币。

## 重新指定客户端 IP 和端口

例如改成另一台电脑的 `192.168.1.20:9200`：

```powershell
.venv\Scripts\python.exe -m tools.prepare_local --server https://192.168.1.20:9200
.venv\Scripts\python.exe -m tools.build_client --server https://192.168.1.20:9200 --output output/client-9200
.\start-server.ps1
```

两个命令中的地址需要一致。输出目录必须使用新目录，工具不覆盖已有客户端。
补丁从原始 APK 生成，不在上一次的修改包上反复修改。
当前原位替换支持最多 40 字节的启动 URL（实际限制由原字符串长度校验）；推荐短 IP/域名。
本补丁使用 HTTPS。原客户端的 WebManager 已经为 HTTPS 配置接受证书的处理器，暂不需要修改系统信任库或 Android 网络配置。
这项行为通过 ARM64 原生代码确认，仍需在实际设备上验证。

## 安装和资源

在没有原游戏存档的测试设备或新模拟器中安装修改 APK。它与官方包签名不同，不能直接覆盖官方安装；不要为测试删除旧设备上的珍贵数据。
包名仍是 `net.commseed.bbm`，需要保留 OBB 的文件名及路径：

```text
/sdcard/Android/obb/net.commseed.bbm/main.43.net.commseed.bbm.obb
```

OBB 来源：`analysis/xapk_1.4.1/Android/obb/net.commseed.bbm/main.43.net.commseed.bbm.obb`。
有已授权的 ADB 连接后，可以执行（如果连了多台设备，先用 `-s 序列号` 指定）：

```powershell
adb install output/client-lan-9100/signed/bbm-local-aligned-debugSigned.apk
adb shell mkdir -p /sdcard/Android/obb/net.commseed.bbm
adb push analysis/xapk_1.4.1/Android/obb/net.commseed.bbm/main.43.net.commseed.bbm.obb /sdcard/Android/obb/net.commseed.bbm/main.43.net.commseed.bbm.obb
```

手机与电脑同 Wi-Fi 时，使用电脑的局域网地址。若没有请求到达日志，检查 Wi-Fi 客户端隔离和 Windows 防火墙；本项目没有自动修改防火墙规则。
只应为实际使用的端口及本地子网放行，不需要路由器端口转发。

Android Studio 标准模拟器通常使用 `10.0.2.2` 访问宿主机，需要相应重新配置服务并生成 APK。其他模拟器的地址规则可能不同。

USB 调试也可以使用 `adb reverse tcp:9100 tcp:9100`：此时客户端和服务的公开地址都配置为 `https://127.0.0.1:9100`。
这里手机的 localhost 通过 ADB 映射到电脑；没有 reverse 时，手机的 localhost 指向手机自身。

### 本机 MuMu 模拟器

本机确认的路径和实例为：

```powershell
$bbmAdb = 'D:\Program Files\Netease\MuMu\nx_main\adb.exe'
$bbmMumu = 'D:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe'

& $bbmMumu control --vmindex 1 launch
& $bbmAdb devices -l
```

实例 1 使用 Android 15。模拟器启动完成并出现在 `devices` 列表后，再安装 APK 和推送 OBB。
注意真实目录是 `nx_main`，不是 `nx\_main`。

## 验证与定位下一步

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m tools.probe
```

18 项测试覆盖独立 .NET 加密样例、HTTPS、账号/会话/钱包持久化、错误签名、过期请求、资源路径限制、原包字符串补丁和完整首屏读取链。
`probe` 验证运行中的版本服务、设备登录和六个连续首屏接口，使用项目证书验证 HTTPS。
`.NET 8` 可选，用于重新生成独立协议样例：

```powershell
dotnet run --project tools/protocol_reference/ProtocolReference.csproj
```

设备联调时预期先出现 `/GetServerInfo` 和 `/Login`，然后依次出现 `/GetUserInfo`、`/GetUserWalletInfo`、`/GetUserEquipInfo`、`/GetUserMonsterInventory`、`/GetUserTownMapInfo`、`/GetUserStoreInfoList`。
其他未实现接口会返回明确失败，不会假装成功保存城市或结算战斗。
下一阶段必须以真机日志和客户端画面为依据，修正初始城市数据并补齐教程触发的第一个写操作。

协议证据与现阶段假设见 [docs/protocol.md](docs/protocol.md)。
