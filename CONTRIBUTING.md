# Technical feedback and reproducible reports

The most useful feedback is a concrete counterexample, an independently
reproduced result, or a precise integration question. Use the bug-report or
technical-review issue form. Code inspection is welcome; state clearly when
you have not executed the tests.

## Include enough information to repeat the observation

- Exact commit SHA and RTL candidate (`control` or `focused`).
- Host OS and architecture, Python/Cocotb versions, simulator and Yosys versions
  relevant to the command, and whether you used Docker or native tools.
- The exact command, clock/baud parameters, and seed when applicable.
- Expected behavior, observed behavior, and the smallest reproducer you found.
- The result JSON and the relevant xUnit entry or log excerpt. A small waveform
  with named signals and a time interval is useful for timing problems.

Preserve failures before rerunning. `make test` is a quick profile;
`make verify` is the full profile. A demo waveform or quick pass does not mean
that the full profile ran. Distinguish compilation, simulator execution, test
assertion failures, evidence validation failures, and timeouts.

Redact credentials, private host paths, usernames, customer information, and
other personal data before posting logs or waveforms. Do not upload `.env`
files, keys, tokens, or proprietary design material.

## Changes and technical discussion

Keep a proposed change focused and explain which behavior it changes. For a
bug fix, include a regression that fails before the fix and passes afterward.
Record the commands actually run; mark skipped or unavailable checks as such.
Do not turn bounded formal checks, generic synthesis counts, or simulation
results into claims about all traces or hardware performance.

If you propose code, identify the provenance and licenses of any third-party
material. Do not include code or data that you lack permission to share. The
public reuse license of this artifact remains undecided; there is no CLA or
additional contributor agreement in this repository.

The maintainer records technical evidence separately from views, stars, forks,
external reproduction, adoption, and revenue. A reviewer's employment or
expertise is not inferred from a GitHub reaction alone.
