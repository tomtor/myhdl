import unittest
import os
import zlib

from myhdl import delay, now, Signal, intbv, ResetSignal, Simulation, \
                  Cosimulation, block, instance, StopSimulation, modbv, \
                  always, always_comb, enum

from deflate import IDLE, WRITE, READ, STARTC, STARTD, LBSIZE

COSIMULATION = True
COSIMULATION = False

if not COSIMULATION:
    from deflate import deflate
else:
    def deflate(i_mode, o_done, i_data, o_data, i_addr, clk, reset):
        print("Cosimulation")
        cmd = "iverilog -o deflate " + \
              "dump.v" + \
              "deflate.v " + \
              "tb_deflate.v "
        os.system(cmd)
        return Cosimulation("vvp -m ./myhdl deflate",
                            i_mode=i_mode, o_done=o_done,
                            i_data=i_data, o_data=o_data, i_addr=i_addr,
                            clk=clk, reset=reset)


def test_data():
    str_data = " ".join(["Hello World!" for _ in range(100)])
    b_data = str_data.encode('utf-8')
    zl_data = zlib.compress(b_data)
    print("From %d to %d bytes" % (len(b_data), len(zl_data)))
    print(zl_data)
    return b_data, zl_data


class TestDeflate(unittest.TestCase):

    def testMain(self):

        def test_decompress(i_mode, o_done, i_data, o_data, i_addr,
                            clk, reset):

            def tick():
                clk.next = not clk

            b_data, zl_data = test_data()

            reset.next = 0
            yield delay(5)
            reset.next = 1
            yield delay(5)

            i_mode.next = WRITE
            for i in range(len(zl_data)):
                i_data.next = zl_data[i]
                i_addr.next = i
                tick()
                yield delay(5)
                tick()
                yield delay(5)
            i_mode.next = IDLE

            i_mode.next = STARTD
            tick()
            yield delay(5)
            tick()
            yield delay(5)
            i_mode.next = IDLE

            print(now())
            while not o_done:
                tick()
                yield delay(5)
                tick()
                yield delay(5)
            print(now())

            last = o_data
            i_mode.next = READ
            d_data = []
            for i in range(last + 1):
                i_addr.next = i
                tick()
                yield delay(5)
                tick()
                yield delay(5)
                d_data.append(bytes([o_data]))
            i_mode.next = IDLE

            d_data = b''.join(d_data)

            self.assertEqual(b_data, d_data, "decompress does NOT match")

        self.runTests(test_decompress)

    def runTests(self, test):
        """Helper method to run the actual tests."""

        i_mode = Signal(intbv(0)[3:])
        o_done = Signal(bool(0))

        i_data = Signal(intbv()[8:])
        o_data = Signal(intbv()[LBSIZE:])
        i_addr = Signal(intbv()[LBSIZE:])

        clk = Signal(bool(0))
        reset = ResetSignal(1, 0, True)

        dut = deflate(i_mode, o_done, i_data, o_data, i_addr, clk, reset)

        check = test(i_mode, o_done, i_data, o_data, i_addr, clk, reset)
        sim = Simulation(dut, check)
        # traceSignals(dut)
        sim.run(quiet=1)


SLOWDOWN = 1

@block
def test_deflate_bench(i_clk, o_led, led0_g):

    d_data = [Signal(intbv()[8:]) for _ in range(2048)]
    b_data, zl_data = test_data()

    TESTDATA = tuple(zl_data)

    """
    tout = Signal(intbv(0)[8:])
    taddr = Signal(intbv(0)[8:])
    @always_comb
    def readtd():
        tout.next = TESTDATA[int(taddr)]
    """

    i_mode = Signal(intbv(0)[3:])
    o_done = Signal(bool(0))

    i_data = Signal(intbv()[8:])
    o_data = Signal(intbv()[LBSIZE:])
    i_addr = Signal(intbv()[LBSIZE:])

    reset = ResetSignal(1, 0, True)

    dut = deflate(i_mode, o_done, i_data, o_data, i_addr, i_clk, reset)

    scounter = Signal(modbv(0)[SLOWDOWN:])
    counter = Signal(modbv(0)[16:])

    @instance
    def clkgen():
        i_clk.next = 0
        while True:
            yield delay(5)
            i_clk.next = not i_clk

    @always(i_clk.posedge)
    def count():
        o_led.next = counter
        if scounter == 0:
            # print(counter)
            counter.next = counter + 1
        scounter.next = scounter + 1

    tb_state = enum('RESET', 'WRITE', 'DECOMPRESS', 'WAIT', 'VERIFY')
    state = Signal(tb_state.RESET)

    tbi = Signal(modbv(0)[15:])

    @always(i_clk.posedge)
    def logic():
        led0_g.next = 0

        if state == tb_state.RESET:
            reset.next = 0
            tbi.next = 0
            state.next = tb_state.WRITE

        elif state == tb_state.WRITE:
            print(tbi)
            led0_g.next = 1
            reset.next = 1
            i_mode.next = WRITE
            i_data.next = TESTDATA[tbi]
            i_addr.next = tbi
            if tbi < len(TESTDATA) - 1:
                tbi.next = tbi + 1
            else:
                state.next = tb_state.DECOMPRESS

        elif state == tb_state.DECOMPRESS:
            i_mode.next = STARTD
            state.next = tb_state.WAIT

        elif state == tb_state.WAIT:
            i_mode.next = IDLE
            if o_done:
                state.next = tb_state.VERIFY
                i_mode.next = READ
                tbi.next = 0
                i_addr.next = 0

        elif state == tb_state.VERIFY:
            if tbi < len(TESTDATA):
                d_data[tbi].next = o_data  # Should compare here!
                tbi.next = tbi + 1
                i_addr.next = tbi + 1
            else:
                state.next = tb_state.RESET

        if counter == 1000:
            raise StopSimulation()

    if SLOWDOWN == 1:
        return clkgen, dut, count, logic
    else:
        return dut, count, logic


"""
@block
def clkgen(i_clk):
    @instance
    def tick():
        i_clk.next = 0
        while True:
            yield delay(5)
            i_clk.next = not i_clk
    return tick

tclk = clkgen(Signal(bool(0)))
tclk.convert(initial_values=True)
"""

tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]),
                        Signal(bool(0)))

SLOWDOWN=24
tb.convert(initial_values=True)

if not COSIMULATION:
    SLOWDOWN=1
    print("convert SLOWDOWN: ", SLOWDOWN)
    tb.convert(name="test_fast_bench", initial_values=True)
    os.system("iverilog -o test_deflate " +
              "test_fast_bench.v dump.v; " +
              "vvp test_deflate")
else:
    print("Start Unit test")
    unittest.main(verbosity=2)
