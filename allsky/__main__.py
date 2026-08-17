"""Command-line entry: `python -m allsky`."""

from __future__ import annotations

import argparse
import os

import uvicorn

from allsky.config import load_config, save_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Garrey All-Sky camera station")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--write-config", action="store_true", help="write config.json with current defaults")
    parser.add_argument("--seed", action="store_true", help="seed a demo night and exit")
    args = parser.parse_args()
    config = load_config()
    if args.write_config:
        save_config(config)
        print("wrote config.json")
        return
    if args.seed:
        os.environ["ALLSKY_NO_CAPTURE"] = "1"
        from allsky.app import seed_demo_night

        day = seed_demo_night(config)
        print(f"seeded demo night {day}")
        return
    uvicorn.run(
        "allsky.app:app",
        host=args.host or config.host,
        port=args.port or config.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
