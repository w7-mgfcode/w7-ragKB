"""Entry point for the Local Files RAG Pipeline."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

from file_watcher import LocalFileWatcher


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
        watcher = LocalFileWatcher(
            pool=pool,
            watch_directory=args.directory,
            config_path=args.config,
        )
        await watcher.initialize_state()
        await watcher.watch_for_changes(interval_seconds=args.interval)
    finally:
        await pool.close()


def main() -> None:
    script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Local Files RAG Pipeline")
    parser.add_argument(
        "--config",
        type=str,
        default=str(script_dir / "config.json"),
        help="Path to configuration JSON file",
    )
    parser.add_argument(
        "--directory",
        type=str,
        default=None,
        help="Directory to watch for files",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between checks",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Local Files RAG Pipeline stopped by user.")
    except Exception as e:
        print(f"Error running Local Files RAG Pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
