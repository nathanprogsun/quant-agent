import os
import sys
from pathlib import Path

_my_dir = os.path.dirname(os.path.abspath(__file__))


def touch_latest_revision() -> None:
    args = sys.argv[1:]
    if not args:
        print("no revision file provided, skipping")
        return
    abs_path = args[0]
    if not abs_path.startswith(_my_dir):
        print(
            f"expected an absolute path of revision file provided under {_my_dir}, but found {abs_path}",
        )
        return
    revision_file = Path(abs_path)
    with open(f"{_my_dir}/latest_revision.txt", "w") as f:
        f.write(f"{revision_file.name}\n")
