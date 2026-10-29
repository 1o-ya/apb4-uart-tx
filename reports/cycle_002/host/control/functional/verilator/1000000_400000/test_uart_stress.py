"""Seeded legal APB traffic with an independent wire-level UART scoreboard."""
from __future__ import annotations

import os
import random
from collections import deque
from typing import Any

import cocotb
from uart_stress_model import BusResponse, StressBench, WireReceiver

ERRORS = ((0, False, "data_read"), (4, True, "status_write"),
          (1, True, "misaligned_write"), (3, False, "misaligned_read"),
          (8, False, "undefined_read"), (0x10000, True, "high_alias_write"),
          (0xFFFFFFFC, False, "high_read"))


def check_receiver_oracle() -> None:
    for divisor in (1, 3, 10):
        for byte in range(256):
            expected = deque([byte])
            receiver = WireReceiver(divisor, expected)
            bits = [0] + [(byte >> bit) & 1 for bit in range(8)] + [1]
            for cycle in range(10 * divisor + 1):
                receiver.observe(cycle, bits[cycle // divisor] if cycle < 10 * divisor else 1)
            assert receiver.decoded == [byte] and not expected
    faults = (([0] + [0] * 8 + [0], [0]),
              ([0] + [0] * 8 + [1], [255]),
              ([0] + [0] * 8 + [1], []))
    for bits, expected_values in faults:
        receiver = WireReceiver(3, deque(expected_values))
        try:
            for cycle in range(31):
                receiver.observe(cycle, bits[cycle // 3] if cycle < 30 else 1)
        except AssertionError:
            continue
        raise AssertionError("receiver oracle accepted malformed or unsolicited frame")


async def check_error(bench: StressBench, index: int) -> None:
    address, write, label = ERRORS[index]
    response, waits = await bench.transfer(address, write, 0xCC, int(write), index % 8)
    assert response == BusResponse(1, 1, 0) and waits == 0
    bench.errors.add(label)


async def mandatory_bus_cases(bench: StressBench, rng: random.Random) -> None:
    strobes = list(range(16))
    rng.shuffle(strobes)
    for strobe in strobes:
        await bench.write(rng.getrandbits(32), strobe, strobe % 8)
        await bench.drain()
    for index in range(len(ERRORS)):
        await check_error(bench, index)
        await bench.write(rng.randrange(256))
        await check_error(bench, index)
        await bench.drain()
    for strobe in range(0, 16, 2):
        await bench.write(0)
        count = bench.accepted
        assert await bench.write(0xFF, strobe) == 0
        assert bench.accepted == count
        bench.noops_busy += 1
        await bench.drain()
    await bench.write(0)
    assert await bench.write(255) == 10 * bench.divisor - 1
    await bench.drain()


async def mandatory_reset_cases(bench: StressBench, rng: random.Random) -> None:
    divisor = bench.divisor
    ages = {"start": rng.randrange(divisor), "data": rng.randrange(divisor, 9 * divisor),
            "stop": rng.randrange(9 * divisor, 10 * divisor)}
    for phase, age in ages.items():
        await bench.write(0)
        await bench.gap(age)
        await bench.reset()
        bench.reset_phases.add(phase)
        await bench.write(0x55)
        await bench.drain()
    await bench.write(0)
    bench.drive(psel=1, penable=0, paddr=0, pwrite=1, pwdata=0xAA, pstrb=1, pprot=7)
    await bench.cycle()
    bench.drive(penable=1)
    assert await bench.cycle() == BusResponse(0, 0, 0)
    await bench.reset()
    bench.waiting_resets += 1
    await bench.write(0xAA)
    await bench.drain()


async def random_traffic(bench: StressBench, rng: random.Random) -> None:
    for _ in range(128):
        choice = rng.randrange(10)
        if choice < 5:
            await bench.write(rng.getrandbits(32), rng.randrange(16) | 1, rng.randrange(8))
        elif choice == 5:
            await check_error(bench, rng.randrange(len(ERRORS)))
        elif choice == 6:
            response, waits = await bench.transfer(4, protection=rng.randrange(8))
            assert response.error == 0 and waits == 0
        elif choice < 9:
            await bench.write(rng.getrandbits(32), rng.randrange(8) * 2, rng.randrange(8))
        else:
            await bench.gap(rng.randrange(1, 3 * bench.divisor + 1))
    await bench.drain()


@cocotb.test()
async def test_seeded_traffic_and_independent_receiver(dut: Any) -> None:
    check_receiver_oracle()
    seed = int(os.environ.get("UART_TEST_SEED", "20261028"))
    clock = int(os.environ.get("CLK_FREQ_HZ", "1000000"))
    baud = int(os.environ.get("BAUD_RATE", "100000"))
    assert clock > 0 and 0 < baud <= clock
    rng = random.Random(seed)
    bench = StressBench(dut, clock, baud, seed)
    await bench.reset()
    await mandatory_bus_cases(bench, rng)
    await mandatory_reset_cases(bench, rng)
    await random_traffic(bench, rng)
    await bench.gap(10 * bench.divisor + 2)
    bench.save_coverage()
