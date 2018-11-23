from math import log2

from myhdl import always, block, Signal, intbv, modbv, Error, ResetSignal, \
    instance

block_size = 64


@block
def deflate(i_de, i_start, o_done,
            i_din, in_addr, in_en,
            o_dout, out_addr, out_en,
            clk, reset):

    """ Deflate (de)compress

    Ports:

    """

    iram = [Signal(intbv()[8:]) for _ in range(block_size)]
    oram = [Signal(intbv()[8:]) for _ in range(block_size)]

    @always(clk.posedge, reset)
    def logic():
        if not reset:
            o_done.next = False
        else:
            if in_en:
                iram[in_addr].next = i_din
            if out_en:
                o_dout.next = oram[out_addr]
            if i_start:
                if not i_de:
                    raise Error("deflate compress not yet implemented")
                i = 0
                for i in range(in_addr+1):
                    oram[i].next = iram[i]
                out_addr.next = i
                o_done.next = True

    return logic


if __name__ == "__main__":
    d = deflate(Signal(bool(0)), Signal(bool(0)), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[16:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[16:]), Signal(bool(0)),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
