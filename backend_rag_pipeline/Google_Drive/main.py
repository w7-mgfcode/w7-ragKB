"""Entry point for the Google Drive RAG Pipeline."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

from drive_watcher import GoogleDriveWatcher


async def run(args: argparse.Namespace) -> None:
    """Create the asyncpg pool, initialize the watcher, and start watching."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL environment variable is required")
        sys.exit(1)

    pool = await asyncpg.create_pool(
        dsn,
        min_size=int(os.getenv("DB_POOL_MIN", "2")),
        max_size=int(os.getenv("DB_POOL_MAX", "5")),
    )

    try:
        watcher = GoogleDriveWatcher(
            pool=pool,
            credentials_path=args.credentials,
            token_path=args.token,
            folder_id=args.folder_id,
            config_path=args.config,
        )
        await watcher.initialize_state()
        await watcher.watch_for_changes(interval_seconds=args.interval)
    finally:
        await pool.close()


def main() -> None:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Google Drive RAG Pipeline")
    parser.add_argument(
        "--credentials",
        type=str,
        default=str(script_dir / "credentials.json"),
        help="Path to Google Drive API credentials file",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=str(script_dir / "token.json"),
        help="Path to Google Drive API token file",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(script_dir / "config.json"),
        help="Path to configuration JSON file",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between checks",
    )
    parser.add_argument(
        "--folder-id",
        type=str,
        default=None,
        help="Google Drive folder ID to watch",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Google Drive RAG Pipeline stopped by user.")
    except Exception as e:
        print(f"Error running Google Drive RAG Pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
