#!/usr/bin/env python3
"""Docker entrypoint for the RAG Pipeline.

Supports both continuous and single-run modes. Initializes an asyncpg
connection pool and passes it to the appropriate pipeline watcher.

Embedding errors are handled per-chunk (logged and skipped) inside the
pipeline — a single failing chunk does not halt the entire run.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict

import asyncpg

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool."""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        logger.error("DATABASE_URL environment variable is required")
        sys.exit(1)

    return await asyncpg.create_pool(
        dsn,
        min_size=int(os.getenv("DB_POOL_MIN", "2")),
        max_size=int(os.getenv("DB_POOL_MAX", "5")),
    )


async def run_single_check(
    pool: asyncpg.Pool, pipeline_type: str, **kwargs
) -> Dict[str, Any]:
    """Run a single check cycle for the specified pipeline.

    Returns a stats dict with files_processed, files_deleted, errors, etc.
    """
    start_time = time.time()

    try:
        if pipeline_type == "local":
            local_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "Local_Files"
            )
            sys.path.insert(0, local_dir)
            from Local_Files.file_watcher import LocalFileWatcher

            watcher = LocalFileWatcher(
                pool=pool,
                watch_directory=kwargs.get("directory"),
                config_path=kwargs.get("config", "config.json"),
            )
            await watcher.initialize_state()
            stats = await watcher.check_for_changes()

        elif pipeline_type == "google_drive":
            gdrive_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "Google_Drive"
            )
            sys.path.insert(0, gdrive_dir)
            from Google_Drive.drive_watcher import GoogleDriveWatcher

            watcher = GoogleDriveWatcher(
                pool=pool,
                config_path=kwargs.get("config", "config.json"),
            )
            await watcher.initialize_state()
            stats = await watcher.check_for_changes()

        else:
            raise ValueError(f"Unknown pipeline type: {pipeline_type}")

        stats["pipeline_type"] = pipeline_type
        stats["run_mode"] = "single"
        stats["total_duration"] = time.time() - start_time
        return stats

    except Exception as e:
        logger.exception("Error in single check for %s pipeline", pipeline_type)
        return {
            "pipeline_type": pipeline_type,
            "run_mode": "single",
            "files_processed": 0,
            "files_deleted": 0,
            "errors": 1,
            "duration": 0.0,
            "total_duration": time.time() - start_time,
            "error_message": str(e),
        }


async def run_continuous(
    pool: asyncpg.Pool, pipeline_type: str, args: argparse.Namespace
) -> None:
    """Run the pipeline in continuous watch mode."""
    if pipeline_type == "local":
        local_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Local_Files"
        )
        sys.path.insert(0, local_dir)
        from Local_Files.file_watcher import LocalFileWatcher

        watcher = LocalFileWatcher(
            pool=pool,
            watch_directory=args.directory,
            config_path=args.config or "config.json",
        )
        await watcher.initialize_state()
        await watcher.watch_for_changes(interval_seconds=args.interval)

    elif pipeline_type == "google_drive":
        gdrive_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Google_Drive"
        )
        sys.path.insert(0, gdrive_dir)
        from Google_Drive.drive_watcher import GoogleDriveWatcher

        watcher = GoogleDriveWatcher(
            pool=pool,
            config_path=args.config or "config.json",
        )
        await watcher.initialize_state()
        await watcher.watch_for_changes(interval_seconds=args.interval)

    else:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")


async def async_main(args: argparse.Namespace) -> None:
    """Async entry point: create pool, run pipeline, clean up."""
    pool = await create_pool()

    try:
        if args.mode == "single":
            logger.info("Running %s pipeline in single-run mode...", args.pipeline)
            stats = await run_single_check(
                pool,
                args.pipeline,
                directory=args.directory,
                config=args.config,
            )

            logger.info("Run Statistics:\n%s", json.dumps(stats, indent=2))
            _exit_from_stats(stats)
        else:
            await run_continuous(pool, args.pipeline, args)
    finally:
        await pool.close()


def _exit_from_stats(stats: Dict[str, Any]) -> None:
    """Exit with an appropriate code based on run stats."""
    if stats.get("errors", 0) == 0:
        sys.exit(0)

    msg = stats.get("error_message", "").lower()
    if "auth" in msg or "credential" in msg:
        logger.error("Authentication error — exit code 3")
        sys.exit(3)
    elif "config" in msg:
        logger.error("Configuration error — exit code 2")
        sys.exit(2)
    else:
        logger.error("Runtime error — exit code 1 (retry recommended)")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Pipeline Docker Entrypoint")
    parser.add_argument(
        "--pipeline",
        type=str,
        choices=["local", "google_drive"],
        default=os.getenv("RAG_PIPELINE_TYPE", "local"),
        help="Which pipeline to run",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["continuous", "single"],
        default=os.getenv("RUN_MODE", "continuous"),
        help="Run mode: continuous or single check",
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument(
        "--directory",
        type=str,
        default=os.getenv("RAG_WATCH_DIRECTORY"),
        help="Directory to watch (local pipeline)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between checks (continuous mode)",
    )

    args = parser.parse_args()

    # Default config paths
    if not args.config:
        if args.pipeline == "local":
            args.config = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Local_Files",
                "config.json",
            )
        elif args.pipeline == "google_drive":
            args.config = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Google_Drive",
                "config.json",
            )

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user")
    except SystemExit:
        raise
    except Exception:
        logger.exception("Fatal error in RAG pipeline")
        sys.exit(1)


if __name__ == "__main__":
    main()
