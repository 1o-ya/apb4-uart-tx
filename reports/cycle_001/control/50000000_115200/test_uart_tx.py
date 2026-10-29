"""Black-box, clock-by-clock APB4 and UART verification for cocotb 2.x."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import cocotb
from cocotb.triggers import Timer

cocotb.log.info("Runtime Python version: %s", sys.version.split()[0])


CLK_FREQ_HZ = int(os.environ.get("CLK_FREQ_HZ", "1000000"))
BAUD_RATE = int(os.environ.get("BAUD_RATE", "100000"))
DIVISOR = (CLK_FREQ_HZ + BAUD_RATE // 2) // BAUD_RATE
HALF_PERIOD_PS = 10**12 // (2 * CLK_FREQ_HZ)
FRAME_CYCLES = 10 * DIVISOR
assert CLK_FREQ_HZ > 0 and 0 < BAUD_RATE <= CLK_FREQ_HZ
assert DIVISOR >= 1 and HALF_PERIOD_PS >= 1


@dataclass(frozen=True)
class Response:
    ready: int
    error: int
    data: int


@dataclass(frozen=True)
class Transfer:
    error: int
    data: int
    wait_cycles: int


class Bench:
    """A manual clock keeps bus response sampling ahead of the active edge."""

    def __init__(self, dut: Any) -> None:
        self.dut = dut
        self.bits: tuple[int, ...] = ()
        self.age = 0
        self.accepted = 0
        self.completed = 0
        self.cycles = 0

    def value(self, name: str) -> int:
        return int(getattr(self.dut, name).value)

    def drive(self, **signals: int) -> None:
        for name, value in signals.items():
            getattr(self.dut, name).value = value

    def idle(self, selected: bool = False) -> None:
        self.drive(psel=int(selected), penable=0, pwrite=0, paddr=0,
                   pwdata=0, pstrb=0, pprot=0)

    def expected_response(self) -> Response:
        if not self.value("rst_n") or not self.value("psel"):
            return Response(0, 0, 0)
        if not self.value("penable"):
            return Response(0, 0, 0)
        address, write = self.value("paddr"), self.value("pwrite")
        if address == 0 and write:
            effective = self.value("pstrb") & 1
            return Response(int(not (effective and self.bits)), 0, 0)
        if address == 4 and not write:
            return Response(1, 0, int(bool(self.bits)))
        return Response(1, 1, 0)

    def check_outputs(self) -> None:
        expected_tx = self.bits[self.age // DIVISOR] if self.bits else 1
        assert self.value("tx") == expected_tx, (
            f"cycle={self.cycles}, frame_age={self.age}, "
            f"tx={self.value('tx')}, expected={expected_tx}, bits={self.bits}"
        )
        expected = self.expected_response()
        actual = Response(self.value("pready"), self.value("pslverr"),
                          self.value("prdata"))
        assert actual == expected, (
            f"cycle={self.cycles}, frame_age={self.age}, "
            f"APB response={actual}, expected={expected}"
        )

    def apply_edge(self, response: Response) -> None:
        if not self.value("rst_n"):
            self.bits, self.age = (), 0
            return
        if self.bits:
            self.age += 1
            if self.age == FRAME_CYCLES:
                self.bits, self.age = (), 0
                self.completed += 1
        accepted = (self.value("psel") and self.value("penable")
                    and response.ready and not response.error)
        if accepted and self.value("pwrite") and self.value("pstrb") & 1:
            assert self.value("paddr") == 0 and not self.bits
            byte = self.value("pwdata") & 0xFF
            self.bits = (0, *((byte >> bit) & 1 for bit in range(8)), 1)
            self.age = 0
            self.accepted += 1

    async def cycle(self) -> Response:
        self.drive(clk=0)
        await Timer(HALF_PERIOD_PS, unit="ps")
        self.check_outputs()
        response = Response(self.value("pready"), self.value("pslverr"),
                            self.value("prdata"))
        self.drive(clk=1)
        await Timer(HALF_PERIOD_PS, unit="ps")
        self.apply_edge(response)
        self.cycles += 1
        self.check_outputs()
        return response

    async def reset(self) -> None:
        self.drive(clk=0, rst_n=0)
        self.idle()
        await Timer(HALF_PERIOD_PS, unit="ps")
        self.bits, self.age = (), 0
        self.check_outputs()
        await self.cycle()
        await self.cycle()
        self.drive(rst_n=1)
        await Timer(1, unit="ps")
        self.check_outputs()

    async def transfer(self, address: int, write: bool = False,
                       data: int = 0, strobe: int = 0, protection: int = 0,
                       keep_selected: bool = False) -> Transfer:
        self.drive(psel=1, penable=0, paddr=address, pwrite=int(write),
                   pwdata=data, pstrb=strobe, pprot=protection)
        await self.cycle()
        self.drive(penable=1)
        for waits in range(FRAME_CYCLES + 8):
            response = await self.cycle()
            if response.ready:
                self.idle(selected=keep_selected)
                return Transfer(response.error, response.data, waits)
        raise AssertionError("APB transfer exceeded one complete UART frame")

    async def write_byte(self, byte: int, **options: Any) -> Transfer:
        result = await self.transfer(0, True, byte, strobe=1, **options)
        assert result.error == 0
        return result

    async def drain(self) -> None:
        while self.bits:
            result = await self.transfer(4)
            assert result.error == 0 and result.wait_cycles == 0
        result = await self.transfer(4)
        assert result == Transfer(0, 0, 0)

    async def assert_idle(self, cycles: int = 4) -> None:
        self.idle()
        for _ in range(cycles):
            await self.cycle()
            assert not self.bits and self.value("tx") == 1


@cocotb.test()
async def test_a_z_and_all_bytes(dut: Any) -> None:
    """Check every bit and its complete duration for A, Z, and all 256 bytes."""
    bench = Bench(dut)
    await bench.reset()
    assert await bench.transfer(4) == Transfer(0, 0, 0)
    for byte in (0x41, 0x5A, *range(256)):
        result = await bench.transfer(0, True, 0xA5C30000 | byte, 0xF)
        assert result == Transfer(0, 0, 0)
        await bench.drain()
    assert bench.accepted == bench.completed == 258
    await bench.assert_idle()


@cocotb.test()
async def test_busy_backpressure_and_back_to_back(dut: Any) -> None:
    """A second write must wait through the final STOP cycle without data loss."""
    bench = Bench(dut)
    await bench.reset()
    first = await bench.write_byte(0x41, keep_selected=True)
    second = await bench.write_byte(0x5A, keep_selected=True)
    assert first.wait_cycles == 0
    assert second.wait_cycles == FRAME_CYCLES - 1
    assert bench.accepted == 2 and bench.completed == 1
    await bench.drain()
    assert bench.completed == 2
    await bench.assert_idle(FRAME_CYCLES + 2)


@cocotb.test()
async def test_strobes_protection_and_bus_gating(dut: Any) -> None:
    """Only PSTRB[0] enables DATA; all PPROT combinations are accepted."""
    bench = Bench(dut)
    await bench.reset()
    for strobe in (0, 2, 4, 8, 14):
        result = await bench.transfer(0, True, 0x41, strobe)
        assert result == Transfer(0, 0, 0)
        await bench.write_byte(0x5A)
        count = bench.accepted
        result = await bench.transfer(0, True, 0x41, strobe)
        assert result == Transfer(0, 0, 0) and bench.accepted == count
        await bench.drain()
    for protection in range(8):
        result = await bench.transfer(0, True, 0xAABBCC41, 15, protection)
        assert result == Transfer(0, 0, 0)
        await bench.drain()
    count = bench.accepted
    bench.drive(psel=0, penable=1, pwrite=1, paddr=0, pwdata=0xFF, pstrb=15)
    await bench.cycle()
    bench.drive(psel=1, penable=0)
    await bench.cycle()
    assert bench.accepted == count and not bench.bits
    bench.drive(penable=1)
    assert (await bench.cycle()).ready == 1
    bench.idle()
    assert bench.accepted == count + 1
    await bench.drain()


@cocotb.test()
async def test_access_errors_have_no_side_effects(dut: Any) -> None:
    """Illegal directions, misalignment, and high-address aliases must error."""
    bench = Bench(dut)
    await bench.reset()
    cases = ((0, False), (4, True), (1, True), (2, False),
             (8, True), (0x10000, True), (0xFFFFFFFC, False))
    for address, write in cases:
        result = await bench.transfer(address, write, 0x41, int(write))
        assert result == Transfer(1, 0, 0)
        await bench.write_byte(0x5A)
        count = bench.accepted
        result = await bench.transfer(address, write, 0x41, int(write))
        assert result == Transfer(1, 0, 0) and bench.accepted == count
        await bench.drain()
    await bench.assert_idle()


@cocotb.test()
async def test_async_reset_aborts_and_recovers(dut: Any) -> None:
    """Assert reset between edges in START, DATA, and STOP, then resend."""
    bench = Bench(dut)
    await bench.reset()
    for age in (0, DIVISOR, 2 * DIVISOR, 9 * DIVISOR, FRAME_CYCLES - 1):
        await bench.write_byte(0x00)
        for _ in range(age):
            await bench.cycle()
        bench.drive(rst_n=0)
        await Timer(max(1, HALF_PERIOD_PS // 2), unit="ps")
        bench.bits, bench.age = (), 0
        bench.check_outputs()
        await bench.reset()
        await bench.write_byte(0x41)
        await bench.drain()
        await bench.assert_idle()


@cocotb.test()
async def test_async_reset_during_stalled_write(dut: Any) -> None:
    """Reset cancels an active frame and a master-aborted waiting transfer."""
    bench = Bench(dut)
    await bench.reset()
    await bench.write_byte(0x00)
    count = bench.accepted
    bench.drive(psel=1, penable=0, paddr=0, pwrite=1,
                pwdata=0x5A, pstrb=15, pprot=5)
    await bench.cycle()
    bench.drive(penable=1)
    assert await bench.cycle() == Response(0, 0, 0)
    assert bench.accepted == count and bench.value("tx") == 0
    bench.drive(rst_n=0)
    await Timer(max(1, HALF_PERIOD_PS // 2), unit="ps")
    bench.bits, bench.age = (), 0
    bench.check_outputs()
    for _ in range(3):
        assert await bench.cycle() == Response(0, 0, 0)
        assert bench.value("tx") == 1 and bench.accepted == count
    bench.idle()
    await bench.cycle()
    await bench.reset()
    await bench.assert_idle(FRAME_CYCLES + 2)
    assert await bench.transfer(4) == Transfer(0, 0, 0)
    assert bench.accepted == count
    await bench.write_byte(0x5A)
    await bench.drain()
    assert bench.accepted == count + 1 and bench.completed == 1


@cocotb.test()
async def test_held_setup_signals_have_no_side_effects(dut: Any) -> None:
    """Defensive gating: PSEL without PENABLE never accepts a DATA write.

    APB requires a one-cycle SETUP phase. Holding these signals for longer
    exercises input gating and is not claimed to be a legal extended SETUP.
    """
    bench = Bench(dut)
    await bench.reset()
    for setup_cycles in (2, 7, FRAME_CYCLES + 3):
        count = bench.accepted
        bench.drive(psel=1, penable=0, paddr=0, pwrite=1,
                    pwdata=0xAABBCC5A, pstrb=15, pprot=7)
        for _ in range(setup_cycles):
            assert await bench.cycle() == Response(0, 0, 0)
            assert bench.accepted == count and not bench.bits
            assert bench.value("tx") == 1
        bench.drive(penable=1)
        assert await bench.cycle() == Response(1, 0, 0)
        bench.idle()
        assert bench.accepted == count + 1
        await bench.drain()
        assert bench.completed == bench.accepted
    await bench.assert_idle()


@cocotb.test()
async def test_demo_a_z(dut: Any) -> None:
    """Emit a compact A/Z waveform using the same pin-only frame oracle."""
    bench = Bench(dut)
    await bench.reset()
    for byte in (0x41, 0x5A):
        assert await bench.write_byte(byte) == Transfer(0, 0, 0)
        await bench.drain()
    assert bench.accepted == bench.completed == 2
    await bench.assert_idle()
