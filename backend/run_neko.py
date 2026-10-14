"""Entry point used by Start_NekoAI.bat and Electron's managed backend."""
import argparse
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the local NekoAI backend")
    parser.add_argument("--data-dir", help="absolute shared app data directory")
    args = parser.parse_args()
    if args.data_dir:
        # Command-line value is authoritative for managed launches so Electron
        # and Python use the same directory even if their environments differ.
        os.environ["NEKO_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())

    from app.launcher import main
    sys.exit(main())
