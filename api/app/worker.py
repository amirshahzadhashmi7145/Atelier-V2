import threading


def _resolve_auto_model(run: dict) -> None:
    """Every run passes through launch() before it executes, so this is the one place
    that guarantees a concrete, available model: it turns an agent's "auto" (or a model
    the provider has removed) into a real one for the run's task, whatever path created
    the run. Without it a run could reach the gateway still named "auto" and fail."""
    try:
        from runtime import automodel
        from store import db

        agent = db.get("agent", run.get("agentId") or "") or {}
        resolved = automodel.resolve(
            run.get("model"), role_key=agent.get("roleKey"), kind=run.get("kind"), text=run.get("task")
        )
        if resolved and resolved != run.get("model"):
            run["model"] = resolved
            if run.get("id"):
                db.put("run", run["id"], run)
    except Exception:
        # Never let model resolution stop a run from launching; the gateway's own error
        # handling will surface a clear message if the model is genuinely unusable.
        pass


def launch(run: dict) -> None:
    _resolve_auto_model(run)
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
