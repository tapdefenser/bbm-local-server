"""Run: python -m bbm.server --config .local/server.json"""
import argparse
import copy
import json
import logging
import ssl
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .config import validate_origin
from .metadata import METADATA_ENTRY, protocol_keys
from .protocol import Codec, ProtocolError, json_bytes, redact
from .state import State

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("bbm")
MAX_BODY = 1024 * 1024


def rooted(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


class Application:
    def __init__(self, config):
        self.config = config
        self.origin = validate_origin(config["public_url"])
        with zipfile.ZipFile(rooted(config["source_apk"])) as apk:
            self.codec = Codec(*protocol_keys(apk.read(METADATA_ENTRY)))
        gameplay_path = rooted(config.get("gameplay_config", "config/gameplay.json"))
        self.gameplay = json.loads(gameplay_path.read_text(encoding="utf-8"))
        self.state = State(rooted(config["database"]), self.gameplay["starting_wallet"])
        self.log_path = rooted(config["request_log"])
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_lock = threading.Lock()
        self.asset_root = rooted(config["asset_root"]).resolve()
        manifest = self.asset_root / "patch_result.json"
        self.assets = {"patch_result.json", "patch_result.bin"}
        if manifest.is_file():
            self.assets.update(x["bundleName"] for x in json.loads(manifest.read_text(encoding="utf-8"))["patchResults"])

    def record(self, entry):
        with self.log_lock, self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), **redact(entry)}, ensure_ascii=False) + "\n")

    def bootstrap(self):
        bundle = {"downloadUrl": self.origin + "/", "BundleVersion": self.config.get("bundle_version", 240),
                  "BundlePath": self.origin + "/bundles"}
        environment = {"url": {"GameServer": self.origin, "BattleServer": self.origin, "ReportServer": self.origin},
                       "aos": bundle, "ios": bundle}
        version = {"Major": 1, "Minor": 4, "Patch": 1, "SkipMarketUpdate": 1}
        return {"serverInfo": {"AppVersion": {"aos": version, "ios": version}, "Main": environment, "Review": environment},
                "maintenanceInfo": {"isOpen": 1, "messageType": 0, "jp": "", "en": "", "kr": "",
                                    "stringKey": "", "arg0": "", "arg1": "", "arg2": "", "isTerminatedBBM": False}}

    def dispatch(self, route, packet, wire):
        tx = packet.get("txId", 0)
        if type(tx) is not int or not (0 <= tx < 2**63):
            raise ProtocolError("txId must be a nonnegative int64")
        response = {"result": 1, "txId": tx}
        if route == "/GetServerInfo":
            response.update(self.bootstrap())
        elif wire != "bbmPacket":
            raise ProtocolError("Game routes require bbmPacket")
        elif route == "/CreateUser":
            response.update(self.state.create())
        elif route == "/IsLoginAble":
            response["result"] = 1 if self.state.exists(text_field(packet, "udid")) else -910001
        elif route == "/LoginUser":
            session = self.state.login(text_field(packet, "udid"), text_field(packet, "accessToken"))
            if session is None:
                response["result"] = -112
            else:
                response.update({"sessionInfo": session, "serverTime": int(time.time()), "opponentName": ""})
        elif route == "/Login":
            # ClientInstance.Login calls SendDevLogin in 1.4.1. Keep this LAN-only.
            if not self.config.get("allow_dev_login", False):
                response["result"] = -112
            else:
                session = self.state.login_dev(text_field(packet, "udid"))
                response.update({"sessionInfo": session, "serverTime": int(time.time()), "opponentName": ""})
        elif not self.state.valid_session(packet.get("userId"), packet.get("sessionId")):
            response["result"] = -910011
        elif route == "/Ping":
            response["serverTime"] = int(time.time())
        elif route == "/GetUserInfo":
            response.update({"userInfo": self.user_info(packet["userId"]), "treasurePoint": 0})
        elif route == "/GetUserWalletInfo":
            response.update({
                "userWalletInfo": self.state.wallet(packet["userId"]),
                "userModeWalletInfo": copy.deepcopy(self.gameplay["mode_wallet"]),
                "lstUserSystemItem": [],
            })
        elif route == "/GetUserEquipInfo":
            response["userEquipInfo"] = copy.deepcopy(self.gameplay["equip"])
        elif route == "/GetUserMonsterInventory":
            response.update(copy.deepcopy(self.gameplay["inventory"]))
        elif route == "/GetUserTownMapInfo":
            target = packet.get("targetUserId")
            if target not in (None, 0, packet["userId"]):
                response["result"] = -205
            else:
                response.update({
                    "userInfoSimple": self.user_info(packet["userId"]),
                    "townMapInfo": self.town_info(packet["userId"]),
                })
        elif route == "/GetUserStoreInfoList":
            response["userItemStoreInfoList"] = []
        elif route == "/GetUserTutorialList":
            response["lstCompletedTutorialId"] = []
        elif route == "/GetUserShield":
            response["shieldLimitTime"] = 0
        elif route == "/GetUserSummonShopInfo":
            response["lstUserSummonShopInfo"] = []
        elif route == "/GetChatServerInfo":
            response["result"] = -5001  # Chat has not been reconstructed.
        else:
            # Never acknowledge gameplay mutations that have not been implemented.
            response.update({"result": -205, "compatStatus": "not_implemented", "route": route})
        return response

    def user_info(self, user_id):
        profile = self.state.profile(user_id)
        town = self.gameplay["town"]
        return {
            "userId": profile["id"], "nickname": profile["nickname"], "exp": 0,
            "lastLoginTime": profile["last_login_at"],
            "mainMonsterId": town["mainMonsterId"],
            "mainMonsterSkinId": town["mainMonsterSkinId"],
            "createdTime": profile["created_at"], "clanId": 0, "clanName": "",
            "trophy": town["trophy"], "totalAssistCount": 0, "likeCount": 0,
        }

    def town_info(self, user_id):
        info = copy.deepcopy(self.gameplay["town"])
        profile = self.state.profile(user_id)
        wallet = self.state.wallet(user_id)
        info.update({
            "userID": user_id, "userName": profile["nickname"],
            "dia": wallet["cash"] + wallet["p_cash"],
            "coin": wallet["coin"], "candy": wallet["candy"], "choco": wallet["choco"],
        })
        return info


def text_field(packet, key):
    value = packet.get(key)
    if not isinstance(value, str) or not (0 < len(value) <= 512):
        raise ProtocolError(f"Invalid {key}")
    return value


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BBMCompat/0.1"

    def setup(self):
        self.request.settimeout(10)
        super().setup()

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        # Standard access log would include arbitrary query parameters.
        pass

    def respond(self, status, data):
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/healthz":
            return self.respond(200, {"status": "ok", "milestone": "login-read-model", "publicUrl": self.app.origin,
                                      "gameplayReady": False})
        if route.startswith("/bundles/"):
            name = unquote(route[len("/bundles/"):])
            # Exact allowlist only; no filesystem path is accepted from the request.
            if name in self.app.assets and "/" not in name and "\\" not in name:
                path = (self.app.asset_root / name).resolve()
                if path.parent == self.app.asset_root and path.is_file():
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(path.stat().st_size))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    with path.open("rb") as f:
                        while True:
                            block = f.read(65536)
                            if not block:
                                break
                            self.wfile.write(block)
                    self.close_connection = True
                    self.app.record({"method": "GET", "route": route, "status": 200})
                    return
        self.app.record({"method": "GET", "route": route[:256], "status": 404})
        self.respond(404, {"error": "not_found"})

    def do_POST(self):
        route = urlsplit(self.path).path
        packet, wire = {}, "unparsed"
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ProtocolError("Transfer-Encoding is not supported")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                raise ProtocolError("Expected one Content-Length")
            size = int(lengths[0])
            if not 0 < size <= MAX_BODY:
                self.respond(413, {"error": "request_too_large_or_empty"})
                return
            self.connection.settimeout(10)
            body = self.rfile.read(size)
            if len(body) != size:
                raise ProtocolError("Incomplete request body")
            packet, wire = self.app.codec.decode(body, self.headers.get("Content-Type", ""))
            result = self.app.dispatch(route, packet, wire)
            self.app.record({"method": "POST", "route": route[:256], "wire": wire,
                             "packet": packet, "result": result["result"]})
            LOG.info("POST %s [%s] result=%s", route[:160], wire, result["result"])
            self.respond(200, result)
        except (ProtocolError, TimeoutError, RecursionError) as exc:
            self.app.record({"method": "POST", "route": route[:256], "wire": wire, "error": type(exc).__name__})
            self.respond(400, {"result": -205, "error": "invalid_packet"})


def make_server(config, app=None):
    app = app or Application(config)
    parsed = urlsplit(app.origin)
    port = config.get("listen_port", parsed.port or (443 if parsed.scheme == "https" else 80))
    server = ThreadingHTTPServer((config.get("listen_host", "127.0.0.1"), port), Handler)
    server.daemon_threads = True
    server.app = app
    if parsed.scheme == "https":
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(rooted(config["tls_cert"]), rooted(config["tls_key"]))
        server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".local/server.json")
    args = parser.parse_args()
    config = json.loads(rooted(args.config).read_text(encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    with make_server(config) as server:
        LOG.info("Login/read-model server at %s (bind %s:%s); gameplay mutations are not implemented", config["public_url"], *server.server_address)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
