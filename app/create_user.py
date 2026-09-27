"""Create a user (or reset a password) from the terminal; the password is asked, never an argument.

uv run python -m app.create_user <username>          # new user
uv run python -m app.create_user <username> --reset  # new password for an existing user
docker compose exec app python -m app.create_user <username>
"""

import argparse
import getpass
import sys

from sqlmodel import Session

from app import auth
from app.db import engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("username")
    parser.add_argument("--reset", action="store_true", help="set a new password")
    args = parser.parse_args(argv)

    # getpass: not echoed, and not left in shell history the way a --password argument would be.
    password = getpass.getpass(f"Password (min {auth.MIN_PASSWORD_LENGTH} characters): ")
    if getpass.getpass("Repeat password: ") != password:
        sys.exit("Passwords don't match.")
    with Session(engine) as session:
        try:
            if args.reset:
                auth.set_password(session, args.username, password)
            else:
                auth.create_user(session, args.username, password)
        except ValueError as e:
            sys.exit(str(e))
    print(f"{'Password updated' if args.reset else 'Created user'}: {args.username}")


if __name__ == "__main__":
    main()
