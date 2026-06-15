import json
import os
import sys


def _load_config() -> dict:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "config.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    config = _load_config()
    from manager import Manager
    return Manager(config).run()


if __name__ == "__main__":
    sys.exit(main())