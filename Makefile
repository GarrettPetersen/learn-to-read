VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
SCRIPT := scripts/generate_cards.py
CONFIG := data/decks.json
OUTPUT := build

.PHONY: all install run clean

all: run

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	touch $(VENV)/bin/activate

install: $(VENV)/bin/activate

run: install
	$(PYTHON) $(SCRIPT) --config $(CONFIG) --output $(OUTPUT)

clean:
	rm -rf $(OUTPUT)
	rm -rf $(VENV)
