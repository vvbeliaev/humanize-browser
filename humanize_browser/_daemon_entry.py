import sys
from pathlib import Path
from humanize_browser.daemon import run_daemon

if __name__ == "__main__":
    headless = sys.argv[2] != "0" if len(sys.argv) > 2 else True
    pid_file = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    run_daemon(int(sys.argv[1]), headless=headless, pid_file=pid_file)
