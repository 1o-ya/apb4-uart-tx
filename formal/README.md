# Bounded formal checks

This gate uses the installed Yosys SAT solver directly. No FPGA, PDK, paid tool,
SBY installation, or external SMT service is needed. From the repository root:

```sh
.venv/bin/python scripts/formal_check.py --out reports/formal_my_first_run
.venv/bin/python -m unittest discover -s tests -p 'test_formal_evidence.py' -v
```

Use a new output directory on each run. A nonzero exit means a failed or
unexecuted gate. Read `verification.json` and each `proof.log`; `proof.ys` is the
actual Yosys command sequence. For a violated property, Yosys writes
`counterexample.vcd`. Successful reachability checks write `reachability.vcd`.

## What is checked

`uart_tx_properties.sv` instantiates the UART through public pins and maintains
an independent reference: the accepted byte becomes a ten-bit START/data/STOP
frame, indexed by elapsed frame clocks. It never reads DUT internal registers.
Every modeled step compares `tx`, `pready`, `pslverr`, and all 32 `prdata` bits
against that model, and checks error-response validity.

Both source candidates are checked at three elaborations:

- clock=10, baud=10, D=1: 32 clock steps.
- clock=20, baud=10, D=2: 52 clock steps.
- clock=25, baud=10, D=3 after rounding: 72 clock steps.

Each depth is `20*D+12`, long enough for two complete UART frames and APB
handshakes after initial reset. This does not force a frame in every trace:
all legal symbolic traces within the bound are checked. A separate satisfying
witness must demonstrate that the assumptions admit a completed frame, a BUSY
write stall, and an error response. This checks that those behaviors are
reachable rather than silently assuming away all interesting traffic.

An intentionally corrupted control RTL, whose bit duration is D-1, must be
rejected by the formal assertions. That fault is a test of the gate, not a
third production candidate. The gate requires a full proof-success message,
zero tool exit status, imported assertions and assumptions, complete log, and
the separate reachability witness. Missing, truncated, error, or timeout logs
do not count as proofs.

## Assumptions and limits

- All addresses/data/protection values are symbolic. Invalid register accesses
  are included; the requester is not assumed to use only valid addresses.
- The APB requester follows SETUP→ACCESS, keeps every required signal stable
  while waiting, drives `PSTRB=0` for reads, and aborts the bus transaction on
  reset. Defensive noncompliant waveforms belong to simulation tests.
- Initial reset is asserted. Reset may recur. One SAT step represents one
  rising clock sample; `async2sync` converts the asynchronous reset into a
  sampled-reset model. Sub-cycle reset pulses, recovery/removal, metastability,
  CDC/RDC, and analog timing are not proved here.
- This is a two-state symbolic check. It is not a four-state X/Z simulation.
- These are bounded proofs of three parameter elaborations. There is no
  induction, no proof for arbitrarily long traces, no proof of all possible
  clock/baud parameters, and no proof of hardware implementation quality.

Primary references: [Yosys SAT command](https://yosyshq.readthedocs.io/projects/yosys/en/v0.51/cmd/sat.html),
[async2sync semantics](https://yosyshq.readthedocs.io/projects/yosys/en/v0.54/cmd/async2sync.html),
[formal Verilog constructs](https://yosyshq.readthedocs.io/projects/sby/en/latest/verilog.html).
The installed tool's `yosys -p 'help sat'` / `help async2sync` were also checked.
