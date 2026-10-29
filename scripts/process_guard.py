"""Bounded POSIX cleanup for a process launched and owned by this test runner.

Unlike a process-group-only kill, ancestry discovery includes live descendants
that called setsid(). It never scans by executable name or kills the user's
other simulator sessions. A descendant already reparented *and* detached before
the first snapshot cannot be safely attributed from Popen alone; untrusted
self-daemonizing programs need OS containment rather than this helper.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any


def _signal_pid(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _has_private_session(pid: int) -> bool:
    try:
        return os.getsid(pid) == pid and os.getpgid(pid) == pid
    except ProcessLookupError:
        return False


def _snapshot() -> dict[int, int]:
    result = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True,
                            text=True, timeout=0.4, check=False)
    if result.returncode != 0:
        raise RuntimeError("Cannot inspect owned process ancestry with ps")
    return {int(pid): int(parent) for line in result.stdout.splitlines()
            for pid, parent in [line.split()]}


def _freeze_descendants(root: int, owned: list[int]) -> None:
    # Parents are stopped before children, so a stopped parent cannot reap and
    # recycle a captured child's PID while this cleanup is in progress.
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        parents = _snapshot()
        found = False
        for parent in list(owned):
            for pid, ppid in parents.items():
                if ppid == parent and pid not in owned:
                    _signal_pid(pid, signal.SIGSTOP)
                    owned.append(pid)
                    found = True
        if not found:
            return
    raise RuntimeError(f"Process tree rooted at {root} did not quiesce within 2.5 seconds")


def terminate_process_tree(proc: subprocess.Popen[Any]) -> None:
    """Stop owned live descendants, including new sessions, and reap the parent.

    The caller must supply its own Popen child. Only an isolated session whose
    leader is this child may be group-signalled; inherited groups are untouched.
    Discovery is bounded to 2.5s plus one 0.4s ps snapshot and 1s parent wait.
    Missing processes are harmless. Inspection/permission failures raise after
    captured processes have been killed, so they are not reported as success.
    """
    if proc.pid <= 1 or proc.pid == os.getpid():
        raise ValueError("Refusing cleanup of a non-child/system process")
    if proc.poll() is not None:
        return
    private_session = _has_private_session(proc.pid)
    owned = [proc.pid]
    try:
        if private_session:
            _signal_group(proc.pid, signal.SIGSTOP)
        else:
            _signal_pid(proc.pid, signal.SIGSTOP)
        _freeze_descendants(proc.pid, owned)
    finally:
        # Signal the group while its stopped leader still exists. On Darwin,
        # killpg after individually killing that leader can return EPERM.
        if private_session:
            _signal_group(proc.pid, signal.SIGKILL)
        for pid in reversed(owned):
            _signal_pid(pid, signal.SIGKILL)
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Owned process did not exit after SIGKILL") from exc
