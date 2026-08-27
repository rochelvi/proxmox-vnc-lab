import argparse

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Proxmox VNC Lab administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("password")
    create.add_argument("--admin", action="store_true")
    subparsers.add_parser("list-users")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        if args.command == "create-user":
            if db.scalar(select(User).where(User.username == args.username)):
                parser.error("username already exists")
            db.add(User(username=args.username, password_hash=hash_password(args.password), is_admin=args.admin))
            db.commit()
            print(f"created user {args.username}")
        else:
            for user in db.scalars(select(User).order_by(User.username)):
                print(f"{user.username}\tadmin={user.is_admin}\tcreated={user.created_at}")


if __name__ == "__main__":
    main()
