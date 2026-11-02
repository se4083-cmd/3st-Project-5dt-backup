"""Loopback-only Uvicorn launcher with a private filesystem shutdown signal."""

import argparse
import asyncio
import os
from pathlib import Path

import uvicorn

from app.config import Settings
from app.local_guard import require_local_database
from app.main import create_app
from scripts.local_support import read_state


async def serve(directory):
    directory, state, env = read_state(directory)
    require_local_database(env["DATABASE_URL"], postgres_only=True)
    os.environ.clear()
    os.environ.update(env)
    settings = Settings(_env_file=directory / "local.env")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=state["api_port"],
            access_log=False,
            log_level="warning",
            proxy_headers=False,
            workers=1,
        )
    )
    stop = directory / "api.stop"

    async def watch():
        while not server.should_exit:
            if server.started and not (directory / "api.started").exists():
                (directory / "api.started").write_text(
                    f"{state['runtime_id']}:{os.getpid()}", encoding="utf-8"
                )
            if stop.exists():
                server.should_exit = True
                return
            await asyncio.sleep(0.2)

    watcher = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        (directory / "api.stopped").write_text("graceful_shutdown\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.state_dir))


if __name__ == "__main__":
    main()
