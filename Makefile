# cinetty: terminal architecture animations from templates.
# Pick a template (make templates), fill a project.yaml, check it, play it in your terminal.

PY      := .venv/bin/python
INPUT   ?=
FORMAT  ?= text
AT      ?= 20
TEST_PATTERN ?= test*.py
LOOP    ?=

.PHONY: help setup setup-photo templates check play preview once test

help:
	@echo "make setup                       install light Python deps for text templates and checks"
	@echo "make setup-photo                 add photo deps and download the models into models/"
	@echo "make templates                   list templates (id, kind, purpose, terminal size, preview)"
	@echo "make check   INPUT=project.yaml  check a project against its template (FORMAT=json for agents)"
	@echo "make play    INPUT=project.yaml  play it in this terminal (LOOP=1 repeats it; Ctrl-C stops)"
	@echo "make once    INPUT=project.yaml  print one frame (AT=seconds)"
	@echo "make test                        run the tests (no terminal window needed)"
	@echo "Record the screen with your own screen recorder."

setup:
	@bash scripts/setup.sh

setup-photo:
	@bash scripts/setup.sh --photo

templates:
	@$(PY) -m cinetty templates --format $(FORMAT)

check:
	@test -n "$(INPUT)" || { echo "usage: make check INPUT=path/to/project.yaml"; exit 2; }
	@$(PY) -m cinetty check "$(INPUT)" --format $(FORMAT)

play:
	@test -n "$(INPUT)" || { echo "usage: make play INPUT=path/to/project.yaml"; exit 2; }
	@bash scripts/play.sh "$(INPUT)" $(if $(LOOP),--loop)

# The older name of play.
preview: play

once:
	@test -n "$(INPUT)" || { echo "usage: make once INPUT=path/to/project.yaml AT=12"; exit 2; }
	@$(PY) -m cinetty once "$(INPUT)" --at $(AT)

test:
	@$(PY) -m unittest discover -s tests -p "$(TEST_PATTERN)"
