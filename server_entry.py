import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.api.main import main
from src.run import cli_entry

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.argv.pop(1)
        cli_entry()
    else:
        main()

