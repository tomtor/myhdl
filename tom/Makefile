PYTHON=python3

#MODULES=fifo.py
MODULES=deflate.py

all: build test

build: $(MODULES)
	for p in $?; do $(PYTHON) $$p; done

test: $(MODULES)
	for p in $?; do $(PYTHON) test_$$p; done

icarus:
	iverilog -o test_fifo test_fifo_bench.v
	vvp test_fifo

clean:
	rm -f *.vcd
