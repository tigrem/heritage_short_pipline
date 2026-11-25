ifeq ($(OS),Windows_NT)
PYTHON ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python)
else
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
endif

.PHONY: validate radio film clean-cache

validate:
	$(PYTHON) -m pipeline.run --stage validate

radio:
	$(PYTHON) -m pipeline.run --stage radio

film:
	$(PYTHON) -m pipeline.run --stage all

clean-cache:
	$(PYTHON) -c "from pipeline.cache import clear_cache; clear_cache()"
