PYTHON ?= venv/bin/python
PIP ?= venv/bin/pip
SYSTEM_PYTHON ?= python3

.PHONY: install install-dev run test test-coverage lint check eval-offline quality

venv/bin/python:
	$(SYSTEM_PYTHON) -m venv venv

venv: venv/bin/python

install: venv
	$(PIP) install -r requirements.txt

install-dev: venv
	$(PIP) install -r requirements-dev.txt

run:
	$(PYTHON) main.py

test:
	$(PYTHON) -m pytest

test-coverage:
	$(PYTHON) -m coverage run -m pytest
	$(PYTHON) -m coverage report --fail-under=82

lint:
	$(PYTHON) -m ruff check .

check:
	$(PYTHON) -m compileall -q main.py config.py sandbox.py agent skills tools utils web scripts system_prompt tests
	node --check web/app.js
	node --check web/metrics.js

eval-offline:
	$(PYTHON) -m evals.offline_runner

quality: check lint test-coverage eval-offline
