PYTHON=python3

MODULES=fifo.py

all: build test

build: $(MODULES)
	for p in $?; do $(PYTHON) $$p; done

test: $(MODULES)
	for p in $?; do $(PYTHON) test_$$p; done
