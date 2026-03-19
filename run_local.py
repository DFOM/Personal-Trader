import os
import signal
import subprocess
import threading
import time
from typing import Optional

from dotenv import load_dotenv

import scheduler


load_dotenv()


def _run_scheduler() -> None:
    scheduler.main()


def main() -> None:
    streamlit_port = os.getenv("STREAMLIT_PORT", "8501")
    streamlit_command = [
        "streamlit",
        "run",
        "ui/app.py",
        "--server.port",
        streamlit_port,
        "--server.address",
        "0.0.0.0",
    ]

    streamlit_process: Optional[subprocess.Popen] = None
    scheduler_thread: Optional[threading.Thread] = None

    try:
        scheduler_thread = threading.Thread(target=_run_scheduler, name="scheduler-main", daemon=True)
        scheduler_thread.start()

        streamlit_process = subprocess.Popen(streamlit_command)

        while True:
            if streamlit_process.poll() is not None:
                raise RuntimeError("Streamlit process exited unexpectedly.")
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass
    finally:
        if streamlit_process is not None and streamlit_process.poll() is None:
            streamlit_process.send_signal(signal.SIGTERM)
            try:
                streamlit_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                streamlit_process.kill()


if __name__ == "__main__":
    main()
