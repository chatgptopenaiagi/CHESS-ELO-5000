"""Owned fault-injection UCI process, not a chess engine or strength fixture."""
import sys

mode = sys.argv[1]
for command in sys.stdin:
    command = command.strip()
    if command == "uci":
        print("id name Controlled UCI fault fixture", flush=True)
        print("uciok", flush=True)
    elif command == "isready":
        print("readyok", flush=True)
    elif command.startswith("go"):
        if mode == "crash":
            sys.exit(7)
        elif mode == "invalid":
            print("info depth 1 score cp 5 pv e2e5", flush=True)
            print("bestmove e2e5", flush=True)
        elif mode == "missing_score":
            print("info depth 1 pv e2e4", flush=True)
            print("bestmove e2e4", flush=True)
        # timeout deliberately supplies no info or bestmove.
    elif command == "quit":
        break
