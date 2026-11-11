PYTHON ?= python3.11
VENV := .venv

.PHONY: setup test clean

# One command after a clean clone.
setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -e '.[dev]'

# Offline: no API key, no network.
test:
	env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN $(VENV)/bin/pytest

clean:
	rm -rf $(VENV) .pytest_cache src/*.egg-info
