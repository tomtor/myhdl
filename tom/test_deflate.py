import unittest
import os
import zlib

from myhdl import delay, now, Signal, intbv, ResetSignal, Simulation, \
                  Cosimulation, block, instance, StopSimulation, modbv, \
                  always

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


@block
def test_deflate_bench(i_clk, o_led):

    i_mode = Signal(intbv(0)[3:])
    o_done = Signal(bool(0))

    i_data = Signal(intbv()[8:])
    o_data = Signal(intbv()[LBSIZE:])
    i_addr = Signal(intbv()[LBSIZE:])

    reset = ResetSignal(1, 0, True)

    dut = deflate(i_mode, o_done, i_data, o_data, i_addr, i_clk, reset)

    d_data = [ Signal(intbv()[8:]) for _ in range(100) ]
    b_data, zl_data = test_data()
    z_data = [ Signal(intbv()[8:]) for i in range(len(zl_data)) ]
    for i in range(len(zl_data)):
        z_data[i].next = zl_data[i]

    counter = Signal(modbv(0)[16:])

    @always(i_clk.posedge)
    def count():
        counter.next = counter + 1

    @always(i_clk.posedge)
    def logic():
        if counter == 5:
            reset.next = 0
            o_led.next = 0
        if counter == 7:
            reset.next = 1
        if counter >=  10 and counter < 50:
            i_mode.next = WRITE
            i_data.next = z_data[counter - 10]
            i_addr.next = counter - 10
        if counter == 50:
            i_mode.next = IDLE

        if counter == 100:
            i_mode.next = STARTD
        if counter == 101:
            i_mode.next = IDLE

        if counter >= 102 and counter < 150:
            i_mode.next = READ
            i_addr.next = counter-102
            if counter >= 103:
              d_data[counter-103].next = o_data
        if counter == 150:
            o_led.next = d_data[0]
            i_mode.next = IDLE

        if counter == 1000:
            raise StopSimulation()

    return dut, count, logic


tb = test_deflate_bench(Signal(bool(0)), Signal(intbv(0)[4:]))

if not COSIMULATION:
    print("convert:")
    tb.convert(initial_values=True)

print("Start Unit test")
unittest.main(verbosity=2)


