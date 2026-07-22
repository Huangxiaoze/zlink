#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remote-desktop",
        description="Cross-platform remote desktop (Python). Host is controlled; client controls.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="launch device-manager GUI (default)")

    host = sub.add_parser("host", help="run controlled endpoint")
    host.add_argument("--bind", default="0.0.0.0", help="listen address")
    host.add_argument("--port", type=int, default=5959)
    host.add_argument("--password", default="", help="connection password (required for 0.0.0.0)")
    host.add_argument("--fps", type=float, default=30.0)
    host.add_argument("--quality", type=int, default=60, help="JPEG quality 30-85")
    host.add_argument("--scale", type=float, default=0.75, help="capture scale 0.4-1.0")
    host.add_argument(
        "--allow-no-password",
        action="store_true",
        help="allow binding without password (local testing only)",
    )

    client = sub.add_parser("client", help="run controller endpoint")
    client.add_argument("--host", required=True, help="host IP / hostname")
    client.add_argument("--port", type=int, default=5959)
    client.add_argument("--password", default="")
    client.add_argument("--fps", type=float, default=30.0)
    client.add_argument("--quality", type=int, default=60)
    client.add_argument("--scale", type=float, default=0.75)
    client.add_argument("--no-reconnect", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
    )

    command = args.command or "gui"

    if command == "gui":
        from remote_desktop.app_gui import run_app

        run_app()
        return 0

    from remote_desktop.client import RemoteClient
    from remote_desktop.config import ClientConfig, HostConfig, NetConfig, StreamConfig
    from remote_desktop.host import RemoteHost

    stream = StreamConfig(max_fps=args.fps, jpeg_quality=args.quality, scale=args.scale).clamp()

    if command == "host":
        net = NetConfig(host=args.bind, port=args.port, password=args.password)
        cfg = HostConfig(net=net, stream=stream, bind_require_password=not args.allow_no_password)
        try:
            RemoteHost(cfg).run()
        except KeyboardInterrupt:
            logging.info("host interrupted")
        return 0

    if command == "client":
        net = NetConfig(host=args.host, port=args.port, password=args.password)
        cfg = ClientConfig(net=net, stream=stream, reconnect=not args.no_reconnect)
        try:
            RemoteClient(cfg).run()
        except KeyboardInterrupt:
            logging.info("client interrupted")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
