import sys
from humanize_browser.daemon import run_daemon

if __name__ == "__main__":
    headless = sys.argv[2] != "0" if len(sys.argv) > 2 else True
    run_daemon(int(sys.argv[1]), headless=headless)
