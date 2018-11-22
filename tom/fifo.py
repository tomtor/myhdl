from math import log2

from myhdl import always, always_seq, instance, block, Signal, ResetSignal, \
  intbv, modbv, delay, StopSimulation, now, Error, Simulation, traceSignals


@block
def fifo(dout, din, rd, wr, empty, full, clk, reset, maxFilling=8, width=8):

    """ Synchronous fifo model

    Ports:
    dout -- data out
    din -- data in
    rd -- read enable
    wr -- write enable
    empty -- empty indication flag
    full -- full indication flag
    clk -- clock input
    maxFilling -- maximum fifo filling
    width -- width of entry

    """

    memory = [Signal(intbv()[width:]) for _ in range(maxFilling)]

    r2 = log2(maxFilling)
    inp = Signal(modbv(0)[r2:])
    outp = Signal(modbv(0)[r2:])

    @always(clk.posedge, reset)
    def access():
        if not reset:
            inp.next = 0
            outp.next = 0
            empty.next = True
            full.next = False
        else:
            if wr:
                if (inp + 1) % maxFilling == outp:
                    raise Error("Full FIFO")
                memory[inp].next = din
                inp.next = inp + 1
                empty.next = False
                full.next = ((inp + 2) % maxFilling == outp)
            if rd:
                if inp == outp:
                    raise Error("Empty FIFO")
                dout.next = memory[outp]
                outp.next = outp + 1
                full.next = False
                empty.next = (inp == outp + 1)

    return access


if __name__ == "__main__":
    width = 8
    cap = 8
    f = fifo(Signal(intbv()[width:]), Signal(intbv()[width:]), Signal(bool(0)),
             Signal(bool(0)), Signal(bool(0)), Signal(bool(0)),
             Signal(bool(0)), Signal(bool(1)), cap, width)
    f.convert(name="fifo8_8")

    width = 32
    cap = 16

    f32 = fifo(Signal(intbv()[width:]), Signal(intbv()[width:]),
               Signal(bool(0)), Signal(bool(0)), Signal(bool(0)),
               Signal(bool(0)), Signal(bool(0)), Signal(bool(1)), cap, width)
    f32.convert(name="fifo32_16")
