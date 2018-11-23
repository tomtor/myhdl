import unittest
import os

from myhdl import instance, block, Signal, ResetSignal,\
    intbv, delay, StopSimulation, now, Simulation, Cosimulation

COSIMULATION = True
# COSIMULATION = False

if not COSIMULATION:
    from fifo import fifo
else:
    def fifo(dout, din, rd, wr, empty, full, clk, reset, maxFilling, width):
        print("Cosimulation")
        cmd = "iverilog -o fifo " + \
              "fifo8_8.v " + \
              "tb_fifo8_8.v "
        os.system(cmd)
        return Cosimulation("vvp -m ./myhdl fifo", dout=dout, din=din, rd=rd,
                            wr=wr, empty=empty, full=full, clk=clk,
                            reset=reset, maxFilling=maxFilling, width=width)


class TestFifo(unittest.TestCase):

    cap = 8

    def testMain(self):

        def test(dout, din, rd, wr, empty, full, clk, reset):
            def tick():
                clk.next = not clk
                # print("Clk:%d" % clk.next)

            reset.next = 0
            yield delay(10)
            reset.next = 1
            yield delay(10)
            for val in range(1, TestFifo.cap):
                # print("Write:", val)
                self.assertTrue(empty == (val == 1))
                wr.next = 1
                din.next = val
                tick()
                yield delay(10)
                self.assertTrue(full == (val == TestFifo.cap-1))
                tick()
                wr.next = 0
                yield delay(10)

            print("Reading...")
            for val in range(1, TestFifo.cap):
                rd.next = 1
                tick()
                yield delay(10)
                self.assertFalse(full)
                tick()
                rd.next = 0
                yield delay(10)
                self.assertEqual(val, dout, "Read matches write")
                # print("Read:", dout)

        self.runTests(test)

    def runTests(self, test):
        """Helper method to run the actual tests."""
        din = Signal(intbv()[8:])
        dout = Signal(intbv()[8:])
        clk = Signal(bool(0))
        wr = Signal(bool(0))
        rd = Signal(bool(0))
        empty = Signal(bool(0))
        full = Signal(bool(0))
        reset = ResetSignal(1, 0, True)
        dut = fifo(dout, din, rd, wr, empty, full, clk, reset, TestFifo.cap, 8)
        check = test(dout, din, rd, wr, empty, full, clk, reset)
        sim = Simulation(dut, check)
        # traceSignals(dut)
        sim.run(quiet=1)


@block
def test_fifo_bench():

    din = Signal(intbv()[8:])
    dout = Signal(intbv()[8:])
    clk = Signal(bool(0))
    wr = Signal(bool(0))
    rd = Signal(bool(0))
    empty = Signal(bool(0))
    full = Signal(bool(0))
    reset = ResetSignal(1, 0, True)

    f8 = fifo(dout, din, rd, wr, empty, full, clk, reset, 4, 8)

    @instance
    def stimulus():

        reset.next = 0
        yield delay(10)
        reset.next = 1
        yield delay(10)

        for l in range(5):
            for i in range(3):
                wr.next = not full
                if full:
                    print("skip wr")
                din.next = (l+1)*(i+1)
                clk.next = not clk
                yield delay(10)
                clk.next = not clk
                yield delay(10)
                print("Now: %d In: %s Empty: %d Full: %d"
                      % (now(), din, empty, full))
            wr.next = 0
            clk.next = not clk
            yield delay(10)
            clk.next = not clk
            yield delay(10)
            for i in range(2):
                rd.next = not empty
                if empty:
                    print("skip rd")
                clk.next = not clk
                yield delay(10)
                clk.next = not clk
                yield delay(10)
                print("Now: %d Out: %s Empty: %d Full: %d"
                      % (now(), dout, empty, full))
            rd.next = 0
            clk.next = not clk
            yield delay(10)

        raise StopSimulation()

    return f8, stimulus


if not COSIMULATION:
    tb = test_fifo_bench()

    print("convert:")
    tb.convert(initial_values=True)

    print("sim:")
    tb.config_sim(trace=False)
    tb.run_sim()

else:
    print("Start Unit test")
    unittest.main(verbosity=2)
