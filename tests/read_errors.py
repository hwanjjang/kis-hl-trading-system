"""Offline doubles for account-read availability failures."""


def read_unavailable(message):
    """A read-availability failure as the venue clients mark it."""
    exc = RuntimeError(message)
    exc.read_unavailable = True
    return exc
