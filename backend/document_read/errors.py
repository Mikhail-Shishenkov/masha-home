"""Controlled reader failures; parser details never cross the application boundary."""


class DocumentReadError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
