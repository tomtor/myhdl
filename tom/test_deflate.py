import unittest
import os
import zlib

from myhdl import delay, now, Signal, intbv, ResetSignal, Simulation,
    Cosimulation

COSIMULATION = True
COSIMULATION = False

if not COSIMULATION:
    from deflate import deflate
else:
    def deflate(i_de, i_start, o_done,
                i_din, in_addr, in_en,
                o_dout, out_addr, out_en,
                clk, reset):
        print("Cosimulation")
        cmd = "iverilog -o deflate " + \
              "deflate.v " + \
              "tb_deflate.v "
        os.system(cmd)
        return Cosimulation("vvp -m ./myhdl deflate",
                            i_de=i_de, i_start=i_start, o_done=o_done,
                            i_din=i_din, in_addr=in_addr, in_en=in_en,
                            o_dout=o_dout, out_addr=out_addr, out_en=out_en,
                            clk=clk, reset=reset)


class TestDeflate(unittest.TestCase):

    def testMain(self):

        def test_data():
            str_data = " ".join(["Hello World!" for _ in range(100)])
            b_data = str_data.encode('utf-8')
            zl_data = zlib.compress(b_data)
            print("From %d to %d bytes" % (len(b_data), len(zl_data)))
            print(zl_data)
            return b_data, zl_data

        def test_decompress(i_de, i_start, o_done,
                            i_din, in_addr, in_en,
                            o_dout, out_addr, out_en,
                            clk, reset):

            def tick():
                clk.next = not clk

            b_data, zl_data = test_data()

            reset.next = 0
            yield delay(5)
            reset.next = 1
            yield delay(5)

            in_en.next = 1
            for i in range(len(zl_data)):
                i_din.next = zl_data[i]
                in_addr.next = i
                tick()
                yield delay(5)
                tick()
                yield delay(5)
            in_en.next = 0

            i_start.next = 1
            tick()
            yield delay(5)
            tick()
            yield delay(5)

            while not o_done:
                tick()
                yield delay(5)
                tick()
                yield delay(5)
                print(now())

            last = out_addr
            out_en.next = 1
            d_data = []
            for i in range(last + 1):
                out_addr.next = i
                tick()
                yield delay(5)
                tick()
                yield delay(5)
                d_data.append(bytes([o_dout]))
            out_en.next = 0

            d_data = b''.join(d_data)

            self.assertEqual(b_data, d_data, "decompress does NOT match")

        self.runTests(test_decompress)

    def runTests(self, test):
        """Helper method to run the actual tests."""

        i_de = Signal(bool(1))  # decompress
        i_start = Signal(bool(0))
        o_done = Signal(bool(0))

        i_din = Signal(intbv()[8:])
        in_addr = Signal(intbv()[16:])
        in_en = Signal(bool(0))

        o_dout = Signal(intbv()[8:])
        out_addr = Signal(intbv()[16:])
        out_en = Signal(bool(0))

        clk = Signal(bool(0))
        reset = ResetSignal(1, 0, True)

        dut = deflate(i_de, i_start, o_done,
                      i_din, in_addr, in_en,
                      o_dout, out_addr, out_en,
                      clk, reset)

        check = test(i_de, i_start, o_done,
                     i_din, in_addr, in_en,
                     o_dout, out_addr, out_en,
                     clk, reset)
        sim = Simulation(dut, check)
        # traceSignals(dut)
        sim.run(quiet=1)


print("Start Unit test")
unittest.main(verbosity=2)
