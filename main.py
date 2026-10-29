"""CLI entrypoint, built on DictationWorker.

For the GUI version see app.py.
"""
import time

import logging_setup
log = logging_setup.init()

from worker import DictationWorker


def main():
    worker = DictationWorker(on_log=lambda m: print(m, flush=True))
    worker.start()
    print("[cli] Ctrl+C to quit. Log:", logging_setup.log_file(), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[exit]")
        worker.stop()


if __name__ == "__main__":
    main()
