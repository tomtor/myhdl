import unittest
import os
import zlib

from myhdl import delay, now, Signal, intbv, ResetSignal, Simulation, \
                  Cosimulation, block, instance, StopSimulation, modbv, \
                  always, always_comb, enum, Error

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
def test_deflate_bench(i_clk, o_led, led0_g, led1_b):

    d_data = [Signal(intbv()[8:]) for _ in range(2048)]
    u_data, c_data = test_data()

    CDATA = tuple(c_data)
    UDATA = tuple(u_data)

    """
    tout = Signal(intbv(0)[8:])
    taddr = Signal(intbv(0)[8:])
    @always_comb
    def readtd():
        tout.next = CDATA[int(taddr)]
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
            counter.next = counter + 1
        scounter.next = scounter + 1

    tb_state = enum('RESET', 'WRITE', 'DECOMPRESS', 'WAIT', 'VERIFY')
    state = Signal(tb_state.RESET)

    tbi = Signal(modbv(0)[15:])

    @always(i_clk.posedge)
    def logic():

        if state == tb_state.RESET:
            led0_g.next = 0
            led1_b.next = 0
            reset.next = 0
            tbi.next = 0
            state.next = tb_state.WRITE

        elif state == tb_state.WRITE:
            print(tbi)
            reset.next = 1
            i_mode.next = WRITE
            i_data.next = CDATA[tbi]
            i_addr.next = tbi
            if tbi < len(CDATA) - 1:
                tbi.next = tbi + 1
            else:
                state.next = tb_state.DECOMPRESS

        elif state == tb_state.DECOMPRESS:
            led0_g.next = 1
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
            led1_b.next = 1
            if tbi < len(CDATA):
                d_data[tbi].next = o_data
                ud = UDATA[tbi]
                if o_data != ud:
                    state.next = tb_state.RESET
                    i_mode.next = IDLE
                    print("FAIL")
                    # raise Error("bad result")
                tbi.next = tbi + 1
                i_addr.next = tbi + 1
            else:
                i_mode.next = IDLE
                state.next = tb_state.RESET

        if counter == 30:
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

SLOWDOWN = 24
tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]),
                        Signal(bool(0)), Signal(bool(0)))

tb.convert(initial_values=True)

if not COSIMULATION:
    SLOWDOWN=1
    tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]),
                            Signal(bool(0)), Signal(bool(0)))
    print("convert SLOWDOWN: ", SLOWDOWN)
    tb.convert(name="test_fast_bench", initial_values=True)
    os.system("iverilog -o test_deflate " +
              "test_fast_bench.v dump.v; " +
              "vvp test_deflate")
else:
    print("Start Unit test")
    unittest.main(verbosity=2)
