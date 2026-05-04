PYTHON ?= python3

.PHONY: install init doctor list run diff compare test update-baseline dashboard agentic-poc-backend agentic-poc-frontend

install:
	$(PYTHON) -m pip install -e .

init:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli init --dir .

doctor:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli doctor -c llmcheck.yaml

list:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli list -c llmcheck.yaml

run:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli run -c llmcheck.yaml

diff:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli diff -c llmcheck.yaml

compare:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli compare -c llmcheck.yaml

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

update-baseline:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli run -c llmcheck.yaml --update-baseline

dashboard:
	PYTHONPATH=src $(PYTHON) -m llmcheck.cli serve -c llmcheck.yaml --host 127.0.0.1 --port 9090

agentic-poc-backend:
	PYTHONPATH=src:apps/agentic-poc/backend $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

agentic-poc-frontend:
	$(PYTHON) -m http.server 4173 --directory apps/agentic-poc/frontend
