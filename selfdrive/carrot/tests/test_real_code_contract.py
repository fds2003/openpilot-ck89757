#!/usr/bin/env python3
"""Real-code TDD contract for carrot_serv.py.

Unlike the mock-based test_cooperative_command_handlers.py (which re-implements
the handler inside MockCarrotServ), this suite extracts and compiles the ACTUAL
_handle_speed_limit_command from carrot_serv.py. It therefore covers the
6986b10 change "clamp minimum cruising speed to 30 kph" and will go RED if the
real handler ever regresses or the clamp is removed.
"""
import ast
import contextlib
import io
import unittest
from pathlib import Path

SERV_PATH = Path(__file__).resolve().parents[1] / "carrot_serv.py"


def _load_real_handler():
    src = SERV_PATH.read_text(encoding="utf-8", errors="replace")
    ast.parse(src)
    lines = src.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines)
                 if l.strip().startswith("def _handle_speed_limit_command"))
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("  def ")), len(lines))
    block = "".join(lines[start:end]).replace("  def ", "def ", 1)
    ns = {}
    exec(compile(block, "<real _handle_speed_limit_command>", "exec"), ns)
    return block, ns["_handle_speed_limit_command"]


_BLOCK, _HANDLER = _load_real_handler()


class _Serv:
    def __init__(self, current):
        self.nRoadLimitSpeed = current
        self.nRoadLimitSpeed_last = current


def _run(arg, current=80):
    serv = _Serv(current)
    with contextlib.redirect_stdout(io.StringIO()):
        _HANDLER(serv, arg)
    return serv


class TestRealCodeContract(unittest.TestCase):

    def test_real_source_carries_30kph_clamp(self):
        # Guard: prove we are testing the real handler, not a shadow copy.
        self.assertIn("if 0 < speed_kph < 30:", _BLOCK)
        self.assertIn("speed_kph = 30", _BLOCK)

    def test_speeds_below_30_clamp_to_30(self):
        for arg in ("1", "15", "29"):
            with self.subTest(arg=arg):
                serv = _run(arg)
                self.assertEqual(serv.nRoadLimitSpeed, 30)
                self.assertEqual(serv.nRoadLimitSpeed_last, 30)

    def test_boundary_and_above_unchanged(self):
        for arg, expected in (("30", 30), ("31", 31), ("100", 100), ("160", 160)):
            with self.subTest(arg=arg):
                serv = _run(arg)
                self.assertEqual(serv.nRoadLimitSpeed, expected)
                self.assertEqual(serv.nRoadLimitSpeed_last, expected)

    def test_invalid_and_out_of_range_keep_previous(self):
        for arg in ("161", "-1", "abc", None):
            with self.subTest(arg=arg):
                serv = _run(arg, current=80)
                self.assertEqual(serv.nRoadLimitSpeed, 80)
                self.assertEqual(serv.nRoadLimitSpeed_last, 80)

    def test_zero_is_accepted_as_zero(self):
        # 6986b10 clamps only 0 < x < 30; 0 is currently accepted verbatim.
        # If the clamp is later widened to include 0, update this contract.
        serv = _run("0")
        self.assertEqual(serv.nRoadLimitSpeed, 0)
        self.assertEqual(serv.nRoadLimitSpeed_last, 0)


if __name__ == "__main__":
    unittest.main()
