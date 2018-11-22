from math import log2
import random
import unittest

from myhdl import always, always_seq, instance, block, Signal, ResetSignal, intbv, modbv, delay,\
  StopSimulation, now, Error, Simulation, traceSignals

from fifo import fifo


class TestFifo(unittest.TestCase):
  
  cap = 4

  def testMain(self):

    def test(dout, din, rd, wr, empty, full, clk, reset):
      def tick():
        clk.next = not clk
        print("Clk:%d" % clk.next)
      
      reset.next = 0
      yield delay(10)
      reset.next = 1
      yield delay(10)
      for val in range(1,TestFifo.cap):
        print("Write:", val)
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
      for val in range(1,TestFifo.cap):
        rd.next= 1
        tick()      
        yield delay(10)
        self.assertFalse(full)        
        tick()
        rd.next = 0
        yield delay(10)
        self.assertEqual(val, dout, "Read matches write")
        print("Read:", dout)

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
    reset = ResetSignal(1,0,True)
    dut= fifo(dout, din, rd, wr, empty, full, clk, reset, TestFifo.cap)
    check = test(dout, din, rd, wr, empty, full, clk, reset)
    sim = Simulation(dut, check)
    #traceSignals(dut)
    sim.run(quiet=1)  
    
@block
def testbench():
  din = Signal(intbv()[8:])
  dout = Signal(intbv()[8:])
  clk = Signal(bool(0))
  wr = Signal(bool(0))
  rd = Signal(bool(0))
  empty = Signal(bool(0))
  full = Signal(bool(0))
  reset = Signal(bool(1)) # ResetSignal(1,0,True)
  
  f8 = fifo(dout, din, rd, wr, empty, full, clk, reset, 8)
  
  @always(delay(10))
  def clkgen():
    clk.next = not clk

  @instance
  def stimulus():
    reset.next= 0
    yield clk.negedge
    reset.next= 1
    yield clk.negedge
    for _ in range(5):    
      wr.next= 1
      for _ in range(3 + random.randint(-1,1)):
        if full:
          pass
        else:
          v = random.randint(1,255)
          din.next = v
          yield clk.negedge
          print("Now: %d In: %s Empty: %d Full: %d" % (now(), hex(v), empty, full))
      wr.next = 0
      yield clk.negedge
      rd.next = 1
      for _ in range(2 + random.randint(-1,1)):
        if empty:
          pass
        else:
          yield clk.negedge
          print("Now: %d Out: %s Empty: %d Full: %d" % (now(), hex(dout), empty, full))
      rd.next = 0
      yield clk.negedge
  
    raise StopSimulation()
  
  return f8, clkgen, stimulus

tb = testbench()
tb.config_sim(trace=True)
tb.run_sim()

#print("Start Unit test")
#unittest.main(verbosity=2)
