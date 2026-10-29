.DEFAULT_GOAL := test
PYTHON ?= .venv/bin/python

.PHONY: test verify thorough regression demo unit formal mutations container-build container-test
test:
	"$(PYTHON)" scripts/qualify.py --profile quick

verify:
	"$(PYTHON)" scripts/qualify.py --profile full

thorough: verify

regression:
	"$(PYTHON)" scripts/verify.py

demo:
	"$(PYTHON)" scripts/verify.py --demo-only

unit:
	"$(PYTHON)" scripts/run_gate.py unit

formal:
	"$(PYTHON)" scripts/run_gate.py formal

mutations:
	"$(PYTHON)" scripts/run_gate.py mutations

container-build:
	docker build -t uart-tx-verify:local .

container-test:
	docker run --rm --user "$$(id -u):$$(id -g)" --mount "type=bind,source=$(CURDIR),target=/workspace" uart-tx-verify:local make verify PYTHON=/opt/venv/bin/python
