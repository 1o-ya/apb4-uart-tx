"""Pin-only APB driver and UART mid-bit decoder, independent of RTL state."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cocotb.triggers import Timer


@dataclass(frozen=True)
class BusResponse:
    ready: int
    error: int
    data: int


class WireReceiver:
    """Detect a falling start edge, then sample ten wire bits at their centers."""

    def __init__(self, divisor: int, expected: deque[int]) -> None:
        self.divisor = divisor
        self.expected = expected
        self.start: int | None = None
        self.samples: dict[int, int] = {}
        self.previous = 1
        self.decoded: list[int] = []

    def abort(self) -> None:
        self.start = None
        self.samples.clear()
        self.previous = 1

    def observe(self, cycle: int, level: int) -> None:
        if self.start is None and self.previous == 1 and level == 0:
            assert self.expected, f"unexpected UART start at cycle {cycle}"
            self.start, self.samples = cycle, {}
        if self.start is not None:
            age = cycle - self.start
            if age < 10 * self.divisor and age % self.divisor == self.divisor // 2:
                self.samples[age // self.divisor] = level
            if age == 10 * self.divisor:
                self.finish()
        self.previous = level

    def finish(self) -> None:
        assert len(self.samples) == 10, f"incomplete UART frame: {self.samples}"
        assert self.samples[0] == 0, f"invalid UART START: {self.samples}"
        assert self.samples[9] == 1, f"invalid UART STOP: {self.samples}"
        byte = sum(self.samples[bit + 1] << bit for bit in range(8))
        assert self.expected, f"unsolicited decoded byte {byte:#04x}"
        wanted = self.expected.popleft()
        assert byte == wanted, f"decoded UART byte={byte:#04x}, expected={wanted:#04x}"
        self.decoded.append(byte)
        self.start, self.samples = None, {}


class StressBench:
    """Derive bus expectations from accepted transfer timestamps, not DUT state."""

    def __init__(self, dut: Any, clock: int, baud: int, seed: int) -> None:
        self.dut, self.seed = dut, seed
        self.divisor = (clock + baud // 2) // baud
        self.half_ps = 10**12 // (2 * clock)
        self.cycles = 0
        self.accepted_at: int | None = None
        self.expected: deque[int] = deque()
        self.receiver = WireReceiver(self.divisor, self.expected)
        self.accepted = self.aborted = self.wait_cycles = 0
        self.transfers = self.idle_gaps = self.noops_busy = 0
        self.strobes: set[int] = set()
        self.protections: set[int] = set()
        self.errors: set[str] = set()
        self.reset_phases: set[str] = set()
        self.waiting_resets = 0

    def value(self, name: str) -> int:
        return int(getattr(self.dut, name).value)

    def drive(self, **signals: int) -> None:
        for name, value in signals.items():
            getattr(self.dut, name).value = value

    def idle(self) -> None:
        self.drive(psel=0, penable=0, pwrite=0, paddr=0, pwdata=0, pstrb=0, pprot=0)

    def busy(self) -> bool:
        return self.accepted_at is not None and self.cycles - self.accepted_at < 10 * self.divisor

    def response(self) -> BusResponse:
        if not self.value("rst_n") or not self.value("psel") or not self.value("penable"):
            return BusResponse(0, 0, 0)
        address, write = self.value("paddr"), self.value("pwrite")
        if address == 0 and write:
            return BusResponse(int(not (self.value("pstrb") & 1 and self.busy())), 0, 0)
        if address == 4 and not write:
            return BusResponse(1, 0, int(self.busy()))
        return BusResponse(1, 1, 0)

    def check_response(self) -> BusResponse:
        actual = BusResponse(self.value("pready"), self.value("pslverr"), self.value("prdata"))
        assert actual == self.response(), (
            f"cycle={self.cycles} response={actual}, expected={self.response()}"
        )
        return actual

    async def cycle(self) -> BusResponse:
        self.drive(clk=0)
        await Timer(self.half_ps, unit="ps")
        response = self.check_response()
        accept = (self.value("rst_n") and self.value("psel") and self.value("penable")
                  and response.ready and not response.error and self.value("pwrite")
                  and self.value("paddr") == 0 and self.value("pstrb") & 1)
        byte = self.value("pwdata") & 255
        self.drive(clk=1)
        await Timer(self.half_ps, unit="ps")
        self.cycles += 1
        if accept:
            self.accepted_at = self.cycles
            self.expected.append(byte)
            self.accepted += 1
        if self.value("rst_n"):
            self.receiver.observe(self.cycles, self.value("tx"))
        else:
            assert self.value("tx") == 1, "TX did not stay idle during reset"
        self.check_response()
        return response

    async def reset(self) -> None:
        self.drive(clk=0, rst_n=1)
        await Timer(1, unit="ps")
        self.drive(rst_n=0)
        await Timer(max(1, self.half_ps // 3), unit="ps")
        self.aborted += len(self.expected)
        self.expected.clear()
        self.accepted_at = None
        self.receiver.abort()
        self.idle()
        assert self.value("tx") == 1, "TX must abort asynchronously before a clock edge"
        self.check_response()
        await self.cycle()
        await self.cycle()
        self.drive(clk=0, rst_n=1)
        await Timer(self.half_ps, unit="ps")
        self.check_response()

    async def transfer(self, address: int, write: bool = False, data: int = 0,
                       strobe: int = 0, protection: int = 0) -> tuple[BusResponse, int]:
        self.drive(psel=1, penable=0, paddr=address, pwrite=int(write),
                   pwdata=data, pstrb=strobe, pprot=protection)
        await self.cycle()
        self.drive(penable=1)
        stable = tuple(self.value(n) for n in ("paddr", "pwrite", "pwdata", "pstrb", "pprot"))
        for waits in range(10 * self.divisor + 4):
            assert stable == tuple(self.value(n) for n in ("paddr", "pwrite", "pwdata", "pstrb", "pprot"))
            response = await self.cycle()
            if response.ready:
                self.wait_cycles += waits
                self.transfers += 1
                if write:
                    self.strobes.add(strobe)
                self.protections.add(protection)
                self.idle()
                return response, waits
        raise AssertionError("APB wait exceeded one UART frame")

    async def write(self, byte: int, strobe: int = 1, protection: int = 0) -> int:
        response, waits = await self.transfer(0, True, byte, strobe, protection)
        assert response.error == 0
        return waits

    async def gap(self, count: int) -> None:
        self.idle()
        self.idle_gaps += int(count > 0)
        for _ in range(count):
            await self.cycle()

    async def drain(self) -> None:
        await self.gap(0)
        for _ in range(10 * self.divisor + 3):
            if not self.busy():
                break
            await self.cycle()
        assert not self.busy() and not self.expected
        assert self.receiver.start is None
        assert self.value("tx") == 1

    def save_coverage(self) -> None:
        assert self.strobes == set(range(16)), self.strobes
        assert self.protections == set(range(8)), self.protections
        assert len(self.errors) >= 7, self.errors
        assert self.reset_phases == {"start", "data", "stop"}, self.reset_phases
        assert self.wait_cycles > 0 and self.noops_busy >= 8 and self.waiting_resets == 1
        assert len(self.receiver.decoded) >= 32 and self.idle_gaps > 0
        assert self.accepted == len(self.receiver.decoded) + self.aborted
        coverage = {"seed": self.seed, "divisor": self.divisor, "cycles": self.cycles,
                    "accepted_frames": self.accepted, "decoded_frames": len(self.receiver.decoded),
                    "aborted_frames": self.aborted, "transfers": self.transfers,
                    "wait_cycles": self.wait_cycles, "idle_gaps": self.idle_gaps,
                    "noops_while_busy": self.noops_busy, "strobes": sorted(self.strobes),
                    "protections": sorted(self.protections), "errors": sorted(self.errors),
                    "reset_phases": sorted(self.reset_phases), "reset_during_wait": self.waiting_resets,
                    "receiver": "falling-start detection and independent mid-bit wire decoding",
                    "receiver_selfcheck": "all 256 synthetic bytes at D1/3/10; bad STOP, wrong byte, unsolicited frame rejected",
                    "coverage_kind": "asserted scenario coverage, not RTL line/toggle coverage"}
        Path("stress_coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
