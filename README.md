# APB4 UART Tx — reproducible PC verification

A small, single-clock UART transmitter: write one byte over APB and observe an
8-N-1 serial frame. The repository includes RTL, a fixed specification,
simulation tests, waveforms, deliberate-fault tests, and bounded formal checks.
No FPGA board, PDK, paid simulator, or external model API is required to run the
checks.

This is a public technical-review snapshot. The public reuse license is
**undecided**; no open-source license grant is asserted. Hardware implementation
and third-party reproduction remain unverified.

## Run the short demo

From the repository root, with Docker running:

```sh
docker build -t uart-tx-verify:local .
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  uart-tx-verify:local make demo PYTHON=/opt/venv/bin/python
```

The first build downloads and compiles the tool environment. It takes longer
than subsequent runs. These commands use a POSIX shell; on Windows, use WSL2 or
the included [VS Code Dev Container](docs/CONTAINER.md).

The demo sends `A` and `Z`. Open `reports/demo/dump.vcd` in the VS Code Surfer
extension and add `clk`, `rst_n`, `psel`, `penable`, `pready`, `pwdata`, and `tx`.
The demo uses a 1 MHz clock and 100000 baud: one bit lasts 10 clock cycles.

With Python 3.11+, Icarus 11+, Make, and `ps` installed, the native setup is:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make demo
make test
```

`make test` is the **quick** profile. `make verify` is the **full** profile and
also requires Verilator 5.036+, its coverage utility, a C++ compiler, and Yosys.
It fails if required tools are missing. To run the full profile in the container:

```sh
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  uart-tx-verify:local make verify PYTHON=/opt/venv/bin/python
```

Each run writes a fresh directory under `reports/runs/` with JSON, xUnit XML,
logs, and relevant waveforms. The latest overall status is
`reports/latest-qualification.json`; check its `profile` as well as `status`.
`reports/demo/` contains the last successful demo, so its presence alone does not
establish that a later qualification passed.

## Interface and behavior

The module is `uart_tx_apb`. `clk` is the APB clock and `rst_n` is asynchronous,
active low. Inputs are `paddr[31:0]`, `psel`, `penable`, `pwrite`,
`pwdata[31:0]`, `pstrb[3:0]`, and `pprot[2:0]`. Outputs are `prdata[31:0]`,
`pready`, `pslverr`, and `tx`.

- `0x00 DATA` is write-only. A completed write with `PSTRB[0]=1` accepts
  `PWDATA[7:0]`. While transmitting, such a write waits with `PREADY=0`.
- `0x04 STATUS` is read-only. Bit 0 is BUSY; all other bits are zero.
- A DATA write with `PSTRB[0]=0` completes as a no-op, including during BUSY.
  Upper data bytes and strobes do not change the serial byte.
- DATA reads, STATUS writes, undefined addresses, and misaligned addresses
  complete with `PSLVERR=1` and no transmit side effects.
- The entire 32-bit byte address is decoded, with no high-address aliases.
  Base-address selection is the integrating system's responsibility.
- Every `PPROT` encoding is accepted. Access policy belongs upstream.
- During reset, deselection, or SETUP, APB response outputs are zero and no
  write is accepted. The requester supplies one SETUP cycle, drives `PSTRB=0`
  on reads, and holds required request signals stable while waiting.

UART framing is START=0, eight data bits LSB first, STOP=1, and idle=1. Parameters
`CLK_FREQ_HZ` and `BAUD_RATE` must be positive signed 32-bit integers, with
`BAUD_RATE <= CLK_FREQ_HZ`. Defaults are 50000000 Hz and 115200 baud.

```text
D = (CLK_FREQ_HZ + BAUD_RATE // 2) // BAUD_RATE
A = 0x41: 0 | 1 0 0 0 0 0 1 0 | 1
Z = 0x5a: 0 | 0 1 0 1 1 0 1 0 | 1
```

Each bit lasts exactly D clocks; BUSY lasts 10D clocks. The next frame can be
accepted on the rising edge after returning to IDLE, giving a queued write at
least one idle clock. There is no FIFO. Reset aborts an active frame and any
unfinished bus transaction; reset release must be synchronized by the
integrating system. Receive, interrupts, runtime baud changes, and security
enforcement are outside this IP's scope.

`rtl/uart_tx_apb.v` is the control implementation.
`candidates/focused/uart_tx_apb.v` changes only the divider counter direction.
Both use the same external specification and tests.

## Recorded local verification

The [saved qualification results](reports/cycle_002/SUMMARY.md) and
[machine-readable summary](reports/cycle_002/SUMMARY.json) record complete runs
on macOS arm64 and Linux arm64. **Each environment separately** passed:

- 288 directed simulation tests: two RTL candidates, two simulators, nine
  clock/baud settings, and eight tests per setting.
- 24 seeded traffic cases using a separate receiver that samples TX bit centers.
- 18 coverage-instrumented tests and two compact A/Z demos.
- Rejection of ten invalid parameter instances.
- Detection of all 12 deliberate single faults, after a passing unmodified
  baseline. These expected failures are counted separately from normal tests.
- Six bounded SAT proofs, six reachability witnesses, and detection of a
  deliberately faulty bit duration.
- 29 unit tests of evidence validation and owned-process cleanup, plus lint,
  generic synthesis, and source-manifest checks.

The macOS run used Python 3.11.15, Icarus 13.0, Verilator 5.052, and Yosys
0.70+post. The Linux run used Python 3.11.18, Icarus 11.0, Verilator 5.036, and
Yosys 0.23. The Dockerfile fixes the base image digest, Python dependencies,
and Verilator source checksum; Debian package resolution is recorded rather
than fully snapshot-pinned. See [container conditions](docs/CONTAINER.md).

Recorded HDL line coverage was 77/82 lines on macOS and 76/81 on Linux, for
both candidates. The default state-recovery branch remained unhit. Counts
depend on the tool's instrumentation and do not establish requirements or
exhaustive branch coverage. Three lint warning categories are explicitly waived
and documented in the [verification record](docs/VERIFICATION.md).

The [GitHub workflow](.github/workflows/regression.yml) runs the full profile.
The archived local results do not assert a GitHub Actions pass; consult the
actual Actions run for the public revision.

## Limits and review questions

The [formal harness](formal/README.md) checks D=1/2/3 for 32/52/72 sampled clock
steps, under a legal APB requester and initial-reset assumptions. It uses a
two-state sampled-reset model. It proves neither unbounded traces nor every
parameter value, sub-cycle asynchronous behavior, metastability, or analog
timing.

No FPGA/ASIC evaluation, place and route, STA, CDC/RDC, DFT, or customer
acceptance has been performed. Generic Yosys cell counts are not area, power,
or Fmax measurements. The relative cell-count ordering of the two candidates
reversed across the recorded environments, so the control remains the baseline.

Technical feedback is welcome, especially reproducible counterexamples:

1. Are the BUSY write wait behavior, reset abortion, and requester assumptions
   specified clearly enough for APB integration?
2. Could a common error survive the cycle reference, separate receiver, and
   formal frame model? What concrete test would expose it?
3. Which boundary, malformed-input, or interrupted-transfer case is missing?
4. Which formal assumptions could hide useful traces, and can a counterexample
   or alternative property demonstrate that?
5. What additional evidence would be necessary before a specific FPGA use?

Please use the technical-review or bug-report issue template and include the
commit, tool versions, command, expected result, and observed result. Mark
commands you have not run. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation, provenance, and license status

- [Japanese VS Code simulation guide](docs/SIMULATION_JA.md).
- [Verification process and limitations](docs/VERIFICATION.md),
  [stress specification](docs/STRESS_SPEC.md), and
  [mutation cases](docs/MUTATIONS.md).
- [Sources and dependency license records](docs/SOURCES.md),
  [source provenance](docs/PROVENANCE.md), and
  [candidate-generation record](docs/candidates.json).

The RTL started from the author's existing personal artifact. External
specifications and example repositories are references; their code is not
incorporated. The original artifact did not supply a LICENSE file. Public reuse
licensing is still undecided, and this snapshot does not claim an open-source
license or production certification.
