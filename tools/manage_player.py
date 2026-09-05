"""Inspect local players or change their persisted wallet values."""
import argparse
import json

from bbm.server import rooted
from bbm.state import State, WALLET_FIELDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".local/server.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    wallet = sub.add_parser("set-wallet")
    wallet.add_argument("--user-id", type=int, required=True)
    for field in WALLET_FIELDS:
        wallet.add_argument("--" + field.replace("_", "-"), dest=field, type=int)
    args = parser.parse_args()

    config = json.loads(rooted(args.config).read_text(encoding="utf-8"))
    gameplay_path = rooted(config.get("gameplay_config", "config/gameplay.json"))
    gameplay = json.loads(gameplay_path.read_text(encoding="utf-8"))
    state = State(rooted(config["database"]), gameplay["starting_wallet"])
    if args.command == "list":
        rows = []
        for user in state.users():
            rows.append({**user, "wallet": state.wallet(user["id"])})
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        changes = {field: getattr(args, field) for field in WALLET_FIELDS if getattr(args, field) is not None}
        print(json.dumps(state.set_wallet(args.user_id, changes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
