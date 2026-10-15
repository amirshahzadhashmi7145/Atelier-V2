class ModelTimeout(Exception):
    pass


class ProviderError(Exception):
    """Provider returned 4xx/5xx; message is safe to show in the run UI."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
