from __future__ import annotations

import argparse
import getpass
import json
import sys

from backend.app import init_db
from backend.client_auth import create_user, list_users, set_active, set_max_devices, set_password


def password_twice() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords do not match")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage GaloDoidoTV client accounts")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a user")
    create.add_argument("username")
    create.add_argument("--max-devices", type=int, default=3)

    password = sub.add_parser("password", help="Change a password and revoke existing sessions")
    password.add_argument("username")

    enable = sub.add_parser("enable", help="Enable a user")
    enable.add_argument("username")

    disable = sub.add_parser("disable", help="Disable a user and revoke sessions")
    disable.add_argument("username")

    limit = sub.add_parser("limit", help="Change device limit")
    limit.add_argument("username")
    limit.add_argument("max_devices", type=int)

    sub.add_parser("list", help="List users")

    args = parser.parse_args()
    init_db()
    try:
        if args.command == "create":
            user_id = create_user(args.username, password_twice(), args.max_devices)
            print(f"Created {args.username.lower()} ({user_id})")
        elif args.command == "password":
            set_password(args.username, password_twice())
            print(f"Password changed for {args.username.lower()}; existing sessions revoked")
        elif args.command == "enable":
            set_active(args.username, True)
            print(f"Enabled {args.username.lower()}")
        elif args.command == "disable":
            set_active(args.username, False)
            print(f"Disabled {args.username.lower()}; sessions revoked")
        elif args.command == "limit":
            set_max_devices(args.username, args.max_devices)
            print(f"Device limit for {args.username.lower()} set to {args.max_devices}")
        elif args.command == "list":
            print(json.dumps(list_users(), indent=2, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
