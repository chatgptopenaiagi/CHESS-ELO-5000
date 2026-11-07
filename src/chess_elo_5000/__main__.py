"""Loopback development server; startup never launches optional workloads."""
import argparse
import ipaddress
from pathlib import Path
from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="CHESS ELO 5000 local chess backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18961)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--engine", type=Path)
    args = parser.parse_args()
    if not ipaddress.ip_address(args.host).is_loopback:
        parser.error("This development backend binds only to a loopback address")
    app = create_app(args.runtime, args.engine)
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False, debug=False)
    finally:
        if "research_lab" in app.extensions:
            app.extensions["research_lab"].shutdown()
        app.extensions["chess_service"].close()


if __name__ == "__main__":
    main()
