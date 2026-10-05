from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .config import load_settings
from .database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="店舗接客システムのDB管理")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="DBとcustomersテーブルを作成します")
    reset_parser = subparsers.add_parser("reset-db", help="全顧客データを削除します")
    reset_parser.add_argument(
        "--yes",
        action="store_true",
        help="削除を確認して実行します",
    )
    args = parser.parse_args()
    if args.command == "reset-db" and not args.yes:
        parser.error("reset-dbには--yesが必要です")

    settings = load_settings()
    database = Database(settings.database_path)
    database.initialize()

    if args.command == "reset-db":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = settings.database_path.parent / "backups" / f"shop-{stamp}.db"
        database.backup(backup_path)
        database.clear_customers()
        print(f"顧客データを初期化しました: {settings.database_path}")
        print(f"復元用バックアップ: {backup_path}")
    else:
        print(f"DBを初期化しました: {settings.database_path}")


if __name__ == "__main__":
    main()
