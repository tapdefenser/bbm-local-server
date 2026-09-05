"""Smoke check of the running local HTTPS service and login read-model chain."""
import argparse
import json
import ssl
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from bbm.metadata import METADATA_ENTRY, protocol_keys
from bbm.protocol import Codec
from bbm.server import rooted

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".local/server.json")
    args = parser.parse_args()
    config = json.loads(rooted(args.config).read_text())
    context = ssl.create_default_context(cafile=str(ROOT/config["tls_cert"]))
    with zipfile.ZipFile(rooted(config["source_apk"])) as apk:
        codec = Codec(*protocol_keys(apk.read(METADATA_ENTRY)))

    def request(path, body=None):
        req = Request(config["public_url"] + path, data=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded"} if body else {})
        with urlopen(req, context=context, timeout=10) as response:
            return json.load(response)

    health = request("/healthz")
    bootstrap = request("/GetServerInfo", b"jsonPacket=%7B%7D")
    login = request("/Login", codec.encode({"osType": 0, "dui": "probe", "udid": "bbm-compat-probe"}))
    session = login["sessionInfo"]
    packet = {"userId": session["userId"], "sessionId": session["sessionId"], "txId": 1}
    routes = ["/GetUserInfo", "/GetUserWalletInfo", "/GetUserEquipInfo",
              "/GetUserMonsterInventory", "/GetUserTownMapInfo", "/GetUserStoreInfoList"]
    results = {}
    for route in routes:
        current = {**packet, "targetUserId": session["userId"]} if route == "/GetUserTownMapInfo" else packet
        results[route] = request(route, codec.encode(current))["result"]
    if health["status"] != "ok" or bootstrap["result"] != 1 or login["result"] != 1 or set(results.values()) != {1}:
        raise SystemExit("Compatibility probe failed")
    print(json.dumps({
        "health": health,
        "bootstrapUrls": bootstrap["serverInfo"]["Main"]["url"],
        "loginUserId": session["userId"],
        "readModelRoutes": results,
    }, indent=2))


if __name__ == "__main__":
    main()
