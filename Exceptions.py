class SyncError(Exception):
    """Exception class from which every exception in this library will derive.
         It enables other projects using this library to catch all errors coming
         from the library with a single "except" statement
    """
    pass


class MonicaFetchError(SyncError):
    """The fetching of an outside Monica resource failed"""
    pass


class GoogleFetchError(SyncError):
    """The fetching of an outside Google resource failed"""
    pass


class BadUserInput(SyncError):
    """Wrong command switch used or otherwise wrong user input"""
    pass


class UserChoice(SyncError):
    """Intended exit chosen by the user"""
    pass


class InternalError(SyncError):
    """An internal error that should not happen (fail save error)"""
    pass
