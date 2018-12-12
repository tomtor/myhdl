PYTHON=python3

MODULES=deflate.py test_deflate.py

all: build test

build: $(MODULES)
	for p in $?; do $(PYTHON) $$p; done

test: icarus icarus10

icarus: build
	iverilog -o test_deflate test_fast_bench.v dump.v
	vvp test_deflate

icarus10: build
	/usr/bin/iverilog -o test_deflate test_fast_bench.v dump.v
	/usr/bin/vvp test_deflate

clean:
	rm -f *.vcd
