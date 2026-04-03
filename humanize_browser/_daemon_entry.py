import sys
from humanize_browser.daemon import run_daemon

if __name__ == "__main__":
    run_daemon(int(sys.argv[1]))
