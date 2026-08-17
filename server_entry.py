import sys
from src.api.main import main
from src.run import cli_entry

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.argv.pop(1)
        cli_entry()
    else:
        main()

