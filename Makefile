PYTHON ?= python3

.PHONY: install init list flagged show review review-latest run-suite test

install:
	$(PYTHON) -m pip install -e ".[test]"

init:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli init --dir .

list:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli list -c llmcheck.yaml

flagged:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli list -c llmcheck.yaml --flagged

show:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli show $$RUN_ID -c llmcheck.yaml

review:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli review $$RUN_ID -c llmcheck.yaml --suite llmcheck_suite.yaml

review-latest:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli review --latest -c llmcheck.yaml --suite llmcheck_suite.yaml

run-suite:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli run-suite -c llmcheck.yaml --suite llmcheck_suite.yaml

test:
	pytest -q
