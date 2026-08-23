class BackupError(RuntimeError):
    """Controlled backup failure; private filesystem details are never exposed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
