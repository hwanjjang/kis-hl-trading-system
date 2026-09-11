"""A process-held account lock shared by CLI workers and signed actions (POSIX)."""
from contextlib import contextmanager
from functools import wraps
import hashlib
import os
from pathlib import Path
import tempfile
import threading

_locks: dict[str, threading.RLock] = {}
_registry_lock = threading.Lock()
_local = threading.local()


@contextmanager
def account_lock(network: str, account: str):
    import fcntl
    key = hashlib.sha256(f'{network.rstrip("/").lower()}:{account.lower()}'.encode()).hexdigest()
    with _registry_lock:
        lock = _locks.setdefault(key, threading.RLock())
    if not lock.acquire(blocking=False):
        raise RuntimeError('Account has another execution owner')
    held = getattr(_local, 'held', set())
    _local.held = held
    fd = None
    try:
        if key not in held:
            path = Path(tempfile.gettempdir()) / f'kis-hl-orders-{os.getuid()}-{key}.lock'
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Account has another execution owner') from exc
            held.add(key)
        yield
    finally:
        if fd is not None:
            held.discard(key)
            os.close(fd)
        lock.release()


def serialized_action(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if kwargs.get('dry_run', True):
            return method(self, *args, **kwargs)
        with account_lock(self.config.base_url, self.config.account_address):
            return method(self, *args, **kwargs)
    return wrapped
