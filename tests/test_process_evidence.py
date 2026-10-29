"""Real-process regressions for nested sessions and isolated cleanup scope."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from scripts.process_guard import terminate_process_tree


def spawn_tree(folder: Path, detached: bool, private_root: bool = True) -> subprocess.Popen[bytes]:
    leaf = "import time; time.sleep(60)"
    middle = ("import pathlib,subprocess,sys,time; "
              f"p=subprocess.Popen([sys.executable,'-c',{leaf!r}],start_new_session={detached!r}); "
              "pathlib.Path('leaf.pid').write_text(str(p.pid)); time.sleep(60)")
    root = ("import pathlib,subprocess,sys,time; "
            f"p=subprocess.Popen([sys.executable,'-c',{middle!r}],start_new_session={detached!r}); "
            "pathlib.Path('middle.pid').write_text(str(p.pid)); time.sleep(60)")
    return subprocess.Popen([sys.executable, "-c", root], cwd=folder,
                            start_new_session=private_root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_for_children(folder: Path) -> list[int]:
    deadline = time.monotonic() + 2
    paths = [folder / "middle.pid", folder / "leaf.pid"]
    while time.monotonic() < deadline:
        try:
            return [int(p.read_text()) for p in paths]
        except (FileNotFoundError, ValueError):
            time.sleep(0.01)
    raise AssertionError("Test process tree did not start")


def process_state(pid: int) -> str:
    result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                            capture_output=True, text=True, timeout=0.5, check=False)
    return result.stdout.strip()


def is_running(pid: int) -> bool:
    state = process_state(pid)
    return bool(state) and not state.startswith("Z")


def cleanup(proc: subprocess.Popen[bytes], children: list[int]) -> None:
    try:
        terminate_process_tree(proc)
    finally:
        for pid in [*reversed(children), proc.pid]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=1)


class ProcessEvidenceTests(unittest.TestCase):
    def test_group_is_killed_before_its_individual_leader(self) -> None:
        proc = MagicMock()
        proc.pid = 12345
        proc.poll.return_value = None
        tracker = MagicMock()
        with patch('scripts.process_guard._has_private_session', return_value=True), \
                patch('scripts.process_guard._freeze_descendants'), \
                patch('scripts.process_guard._signal_group') as group, \
                patch('scripts.process_guard._signal_pid') as pid:
            tracker.attach_mock(group, 'group')
            tracker.attach_mock(pid, 'pid')
            terminate_process_tree(proc)
        kills = [call for call in tracker.mock_calls if call.args[-1] == signal.SIGKILL]
        self.assertEqual(kills[0][0], 'group')
        proc.wait.assert_called_once_with(timeout=1)

    def check_tree(self, detached: bool, private_root: bool = True) -> None:
        with tempfile.TemporaryDirectory() as folder:
            proc = spawn_tree(Path(folder), detached, private_root)
            sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                       start_new_session=True)
            children: list[int] = []
            try:
                children = wait_for_children(Path(folder))
                if detached:
                    self.assertTrue(all(os.getsid(pid) == pid for pid in children))
                with self.assertRaises(subprocess.TimeoutExpired):
                    proc.wait(timeout=0.05)
                started = time.monotonic()
                terminate_process_tree(proc)
                self.assertLess(time.monotonic() - started, 5)
                self.assertIsNotNone(proc.returncode)
                deadline = time.monotonic() + 1
                while any(is_running(pid) for pid in children) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(all(not is_running(pid) for pid in children))
                self.assertIsNone(sibling.poll(), "Unrelated sibling was killed")
                self.assertFalse(process_state(sibling.pid).startswith(("T", "t")),
                                 "Unrelated sibling was stopped")
            finally:
                cleanup(proc, children)
                cleanup(sibling, [])

    def test_nested_detached_sessions_are_stopped_and_sibling_survives(self) -> None:
        self.check_tree(detached=True)

    def test_same_session_timeout_stops_all_descendants(self) -> None:
        self.check_tree(detached=False)

    def test_inherited_group_does_not_kill_calling_process(self) -> None:
        self.check_tree(detached=True, private_root=False)

    def test_already_exited_child_is_safe(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait(timeout=1)
        terminate_process_tree(proc)
        self.assertEqual(proc.returncode, 0)
