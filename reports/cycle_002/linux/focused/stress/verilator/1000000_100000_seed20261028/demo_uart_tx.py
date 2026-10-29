"""One test module so compact waveform runs cannot silently filter all tests."""
from __future__ import annotations

from typing import Any
import cocotb
from test_uart_tx import Bench, Transfer


@cocotb.test()
async def test_demo_a_z(dut: Any) -> None:
    bench = Bench(dut)
    await bench.reset()
    for byte in (0x41, 0x5A):
        assert await bench.write_byte(byte) == Transfer(0, 0, 0)
        await bench.drain()
    assert bench.accepted == bench.completed == 2
    await bench.assert_idle()
