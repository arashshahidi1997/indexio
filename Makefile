PYTHON ?= python
PUBLISH ?= /storage2/arash/infra/bin/publish_pypi.sh
DATALAD ?= /storage/share/python/environments/Anaconda3/envs/cogpy/bin/datalad
MSG ?= Update indexio

RUNTIME_PATH := $(patsubst %/,%,$(dir $(DATALAD))):$(patsubst %/,%,$(dir $(PYTHON))):$(patsubst %/,%,$(dir $(PUBLISH)))
export PATH := $(RUNTIME_PATH):$(PATH)

.PHONY: help dev test build check clean save push publish publish-test

help:
	@printf '%s\n' \
		'make dev           # install editable package with dev extras' \
		'make test          # run test suite' \
		'make build         # build wheel and sdist' \
		'make check         # run twine check on dist artifacts' \
		'make clean         # remove local build artifacts' \
		'make publish       # publish to PyPI via personal helper' \
		'make publish-test  # publish to TestPyPI via personal helper'

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	PYTHONPATH=src $(PYTHON) -m pytest tests -q

build:
	$(PYTHON) -m build

check:
	$(PYTHON) -m twine check dist/*

clean:
	rm -rf build dist .pytest_cache .mypy_cache src/*.egg-info src/indexio.egg-info

publish:
	$(PUBLISH) .

publish-test:
	$(PUBLISH) --test .

-include .projio/projio.mk
