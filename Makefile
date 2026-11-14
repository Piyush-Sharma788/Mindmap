PYTHON ?= python3.11
VENV := .venv

.PHONY: setup test run clean

# One command after a clean clone.
setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -e '.[dev]'

# Offline: no API key, no network.
test:
	env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN $(VENV)/bin/pytest

# Everything in one go: setup if needed, tests, offline evals, live demo if a key is set.
run:
	PYTHON=$(PYTHON) ./run.sh

clean:
	rm -rf $(VENV) .pytest_cache src/*.egg-info
