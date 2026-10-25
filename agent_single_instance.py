"""Cross-platform advisory single-instance guard for opt-in research workers.

The lock is OS-managed (released on process crash), scoped to state directory.
"""
from contextlib import contextmanager
from pathlib import Path
import os


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def research_lock(state_dir):
    directory = Path(state_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "agent-research.lock"
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            # Ensure a byte exists before Windows byte-range locking.
            if not handle.read(1):
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise AlreadyRunning("已有另一個 Agent 研究排程器使用此資料目錄") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise AlreadyRunning("已有另一個 Agent 研究排程器使用此資料目錄") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
