import unittest
import os

from myhdl import instance, block, Signal, ResetSignal, always, \
    intbv, delay, StopSimulation, now, Simulation, Cosimulation

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

        def test(i_de, i_start, o_done,
                 i_din, in_addr, in_en,
                 o_dout, out_addr, out_en,
                 clk, reset):

            @always(delay(5))
            def drive_clk():
                clk.next = not clk

            reset.next = 0
            yield delay(5)
            reset.next = 1
            yield delay(5)

            i_din.next = 0xDE
            in_addr.next = 0
            in_en.next = 1
            yield clk.negedge
            in_en.next = 0

            i_start.next = 1
            yield clk.negedge

            out_addr.next = 0
            out_en.next = 1
            yield clk.negedge
            out_en.next = 0

            self.assertEqual(i_din, o_dout, "Read matches write")

        self.runTests(test)

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
