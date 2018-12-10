PYTHON=python3

MODULES=deflate.py

all: build test

build: $(MODULES)
	for p in $?; do $(PYTHON) $$p; done

test: $(MODULES)
	for p in $?; do $(PYTHON) test_$$p; done

icarus: build
	iverilog -o test_deflate test_fast_bench.v dump.v
	# vvp test_deflate

clean:
	rm -f *.vcd
