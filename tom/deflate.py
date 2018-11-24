from math import log2

from myhdl import always, block, Signal, intbv, Error, ResetSignal, \
    instance, enum

IDLE, WRITE, READ, STARTC, STARTD = range(5)

BSIZE = 64
LBSIZE = log2(BSIZE)


@block
def deflate(i_mode, o_done, i_data, o_data, i_addr, clk, reset):

    """ Deflate (de)compress

    Ports:

    """

    iram = [Signal(intbv()[8:]) for _ in range(BSIZE)]
    oram = [Signal(intbv()[8:]) for _ in range(BSIZE)]

    isize = Signal(intbv()[LBSIZE:])

    @always(clk.posedge, reset)
    def logic():
        if not reset:
            o_done.next = False
        else:
            if i_mode == WRITE:
                iram[i_addr].next = i_data
                isize.next = i_addr
            elif i_mode == READ:
                o_data.next = oram[i_addr]
            elif i_mode == STARTC:
                raise Error("deflate compress not yet implemented")

            elif i_mode == STARTD:
                i = 0
                for i in range(isize + 1):
                    oram[i].next = iram[i]
                o_data.next = i

                # Read block header

                o_done.next = True

    return logic


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[16:]),
                Signal(intbv()[16:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
