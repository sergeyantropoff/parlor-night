"""Печатает DATABASE_URL для секрета Kubernetes. Пароль в вывод команды не попадает отдельно."""

from __future__ import annotations

import os
import sys
import urllib.parse


def main() -> None:
    key = os.environ.get("SECRET_KEY", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    if len(key) < 32:
        print("SECRET_KEY должен быть не короче 32 символов", file=sys.stderr)
        raise SystemExit(1)
    if not password:
        print("Задайте POSTGRES_PASSWORD", file=sys.stderr)
        raise SystemExit(1)
    user = urllib.parse.quote(os.environ.get("POSTGRES_USER", "boardmentor"), safe="")
    quoted_password = urllib.parse.quote(password, safe="")
    database = urllib.parse.quote(os.environ.get("POSTGRES_DB", "boardmentor"), safe="")
    host = os.environ["DB_HOST"]
    print(f"postgresql://{user}:{quoted_password}@{host}:5432/{database}")


if __name__ == "__main__":
    main()
