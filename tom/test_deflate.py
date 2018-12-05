import unittest
import os
import zlib
import random

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
              "deflate.v " + \
              "tb_deflate.v "
              # "dump.v "
        os.system(cmd)
        return Cosimulation("vvp -m ./myhdl deflate",
                            i_mode=i_mode, o_done=o_done,
                            i_data=i_data, o_data=o_data, i_addr=i_addr,
                            clk=clk, reset=reset)


def test_data():
    if 1:
        str_data = " ".join(["Hello World! " + str(1) + " "
                             for i in range(100)])
        b_data = str_data.encode('utf-8')
    else:
        b_data = bytes([random.randrange(0,0x100) for i in range(100)])
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
            for i in range(last):
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
def test_deflate_bench(i_clk, o_led, led0_g, led1_b, led2_r):

    d_data = [Signal(intbv()[8:]) for _ in range(2048)]
    u_data, c_data = test_data()

    CDATA = tuple(c_data)
    UDATA = tuple(u_data)

    i_mode = Signal(intbv(0)[3:])
    o_done = Signal(bool(0))

    i_data = Signal(intbv()[8:])
    u_data = Signal(intbv()[8:])
    o_data = Signal(intbv()[LBSIZE:])
    i_addr = Signal(intbv()[LBSIZE:])

    reset = ResetSignal(1, 0, True)

    dut = deflate(i_mode, o_done, i_data, o_data, i_addr, i_clk, reset)

    tb_state = enum('RESET', 'WRITE', 'DECOMPRESS', 'WAIT', 'VERIFY')
    state = Signal(tb_state.RESET)

    tbi = Signal(modbv(0)[15:])

    scounter = Signal(modbv(0)[SLOWDOWN:])
    counter = Signal(modbv(0)[16:])

    wtick = Signal(bool(0))

    @instance
    def clkgen():
        reset.next = 0
        i_clk.next = 0
        while True:
            yield delay(5)
            i_clk.next = not i_clk
            if state == tb_state.WRITE:
                reset.next = 1

    @always(i_clk.posedge)
    def count():
        if not reset:
            counter.next = 0
            scounter.next = 0
        else:
            o_led.next = counter
            if scounter == 0:
                counter.next = counter + 1
            scounter.next = scounter + 1

    @always(i_clk.posedge)
    def logic():

        if not reset:
            led0_g.next = 0
            led1_b.next = 0
            led2_r.next = 0
            #reset.next = 0
            tbi.next = 0
            state.next = tb_state.WRITE

        elif SLOWDOWN > 1 and scounter != 0:
        #elif scounter != 0:
            pass

        elif state == tb_state.WRITE:
            if tbi < len(CDATA):
                print(tbi)
                led2_r.next = not led2_r
                i_mode.next = WRITE
                i_data.next = CDATA[tbi]
                i_addr.next = tbi
                tbi.next = tbi + 1
            else:
                i_mode.next = IDLE
                state.next = tb_state.DECOMPRESS

        elif state == tb_state.DECOMPRESS:
            led0_g.next = 1
            i_mode.next = STARTD
            state.next = tb_state.WAIT

        elif state == tb_state.WAIT:
            if i_mode == STARTD:
                print("WAIT")
                i_mode.next = IDLE
            elif o_done:
                state.next = tb_state.VERIFY
                tbi.next = 0
                i_addr.next = 0
                i_mode.next = READ
                u_data.next = UDATA[0]
                wtick.next = True

        elif state == tb_state.VERIFY:
            print("VERIFY", o_data)
            led1_b.next = 1
            if wtick:
                wtick.next = False
            elif tbi < len(UDATA):
                d_data[tbi].next = o_data
                ud = u_data
                if o_data != ud:
                    state.next = tb_state.RESET
                    i_mode.next = IDLE
                    print("FAIL", len(UDATA), tbi, ud, o_data)
                    raise Error("bad result")
                u_data.next = UDATA[tbi+1]
                tbi.next = tbi + 1
                i_addr.next = tbi + 1
                wtick.next = True
            else:
                print(len(UDATA))
                print("ALL OK!", tbi)
                i_mode.next = IDLE
                state.next = tb_state.RESET
                raise StopSimulation()

        """
        if now() > 100000:
            raise StopSimulation()
        """

    if SLOWDOWN == 1:
        return clkgen, dut, count, logic
    else:
        return dut, count, logic


if not COSIMULATION:
    SLOWDOWN = 24

    tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]),
                        Signal(bool(0)), Signal(bool(0)), Signal(bool(0)))

    tb.convert(initial_values=False)

if 1:
    SLOWDOWN = 1
    tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]),
                            Signal(bool(0)), Signal(bool(0)), Signal(bool(0)))
    print("convert SLOWDOWN: ", SLOWDOWN)
    tb.convert(name="test_fast_bench", initial_values=False)
    os.system("iverilog -o test_deflate " +
              "test_fast_bench.v dump.v; " +
              "vvp test_deflate")
else:
    print("Start Unit test")
    unittest.main(verbosity=2)
