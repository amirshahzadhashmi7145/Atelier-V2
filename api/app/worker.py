import threading


def start_run(run_id: str) -> None:
    threading.Thread(target=_drive, args=(run_id,), daemon=True).start()


def _drive(run_id: str) -> None:
    from runtime.loop import drive

    drive(run_id)
