from math import log2

from myhdl import always, always_seq, instance, block, Signal, ResetSignal, intbv, modbv, delay,\
  StopSimulation, now, Error, Simulation, traceSignals

@block
def fifo(dout, din, rd, wr, empty, full, clk, reset, maxFilling, width=8):

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
        empty.next = 1
        full.next = 0
      else:
        if wr:
          if (inp.next + 1) % maxFilling == outp:
            raise Error("Full FIFO")
          memory[inp].next = din.val
          inp.next = inp + 1       
        if rd:
          if inp == outp:
            raise Error("Empty FIFO")
          dout.next = memory[outp]
          outp.next = outp + 1
        empty.next = (inp.next == outp.next)
        full.next = ((inp.next + 1) % maxFilling == outp.next)
        
    return access


width=32
cap=16

f32 = fifo(Signal(intbv()[width:]), Signal(intbv()[width:]), Signal(bool(0)), Signal(bool(0)),
             Signal(bool(0)), Signal(bool(0)), Signal(bool(0)), ResetSignal(0,0,True), cap, width)
f32.convert(name="fifo32_16")
