import threading


def launch(run: dict) -> None:
    if run.get("kind") == "lead":
        from runtime.supervisor.graph import start_supervisor

        start_supervisor(run)
        return
    start_run(run["id"])


def start_run(run_id: str) -> None:
    threading.Thread(target=_drive, args=(run_id,), daemon=True).start()


def _drive(run_id: str) -> None:
    from runtime.loop import _fail, drive
    from store import db

    try:
        drive(run_id)
    except Exception as exc:
        try:
            run = db.get("run", run_id)
        except Exception:
            return
        if run and run.get("status") == "running":
            from gateway.exceptions import ProviderError
            from gateway.openai_gateway import model_call_error_message

            provider = (run.get("model") or {}).get("provider") if run else None
            if isinstance(exc, ProviderError):
                message = exc.message
            else:
                message = model_call_error_message(exc, provider) or f"The run stopped because of an unexpected error ({type(exc).__name__}: {exc})"
            try:
                _fail(run, "error", message, [])
            except Exception:
                return
