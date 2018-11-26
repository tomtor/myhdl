from math import log2

from myhdl import always, block, Signal, intbv, Error, ResetSignal, \
    instance, enum

IDLE, WRITE, READ, STARTC, STARTD = range(5)

BSIZE = 256
LBSIZE = log2(BSIZE)

d_state = enum('IDLE', 'HEADER', 'TREE', 'DATA')


@block
def deflate(i_mode, o_done, i_data, o_data, i_addr, clk, reset):

    """ Deflate (de)compress

    Ports:

    """

    iram = [Signal(intbv()[8:]) for _ in range(BSIZE)]
    oram = [Signal(intbv()[8:]) for _ in range(BSIZE)]

    isize = Signal(intbv()[LBSIZE:])
    state = Signal(d_state.IDLE)
    method = Signal(intbv()[2:])
    final = Signal(bool(0))

    numLiterals = Signal(intbv()[9:])
    numDistance = Signal(intbv()[6:])
    numCodeLength = Signal(intbv()[5:])

    CodeLengths = 19
    codeLength = [Signal(intbv()[3:]) for _ in range(CodeLengths)]

    di = Signal(intbv()[LBSIZE:])
    dio = Signal(intbv()[3:])
    do = Signal(intbv()[LBSIZE:])

    def get(d1, d2, offset, width):
        """
        print("d:%s %s offset: %d dio:%d w:%d"
              % (hex(d1), hex(d2), offset, dio, width))
              """
        # r = ((d1 << (dio + offset)) & 0xFF) >> (8 - width)
        r = ((((d1 << 8) | d2) << (dio + offset)) & 0xFFFF) >> (16 - width)
        print(r)
        return r

    def adv(width):
        if dio + width > 7:
            di.next = di + 1
        dio.next = (dio + width) % 8

    @always(clk.posedge, reset)
    def logic():
        if not reset:
            state.next = d_state.IDLE
            o_done.next = False
        else:
            if i_mode == IDLE:

                if state == d_state.HEADER:

                    """
                    # Read block header
                    if di == 0:
                        print(iram[di])
                        if iram[di] == 0x78:
                            print("deflate mode")
                        else:
                            raise Error("unexpected mode")
                    elif di == 1:
                        print(iram[di])
                        if iram[di] != 0x9c:
                            raise Error("unexpected level")
                    elif di >= 6:
                    """

                    d1 = iram[di]
                    # d2 = iram[di+1]
                    if get(d1.val, 0, 0, 1):
                        print("final")
                        final.next = True
                    method.next = get(d1.val, 0, 1, 2)
                    print("method: %d" % method.next)
                    adv(3)
                    state.next = d_state.TREE

                elif state == d_state.TREE:

                    d1 = iram[di]

                    numLiterals = 257 + get(d1.val, 0, 0, 5)
                    d1 = iram[di+1]
                    d2 = iram[di+2]
                    numDistance = 1 + get(d1.val, d2.val, 0, 5)
                    numCodeLength = 4 + get(d1.val, d2.val, 5, 4)

                    d1 = iram[di+2]
                    d2 = iram[di+3]
                    codeLength[16].next = get(d1.val, d2.val, 1, 3)
                    codeLength[17].next = get(d1.val, d2.val, 4, 3)
                    codeLength[18].next = get(d1.val, d2.val, 7, 3)
                    codeLength[0].next = get(d1.val, d2.val, 10, 3)
                    codeLength[8].next = get(d1.val, d2.val, 13, 3)
                    d1 = iram[di+4]
                    d2 = iram[di+5]
                    codeLength[7].next = get(d1.val, d2.val, 0, 3)
                    codeLength[9].next = get(d1.val, d2.val, 3, 3)
                    codeLength[6].next = get(d1.val, d2.val, 6, 3)
                    codeLength[10].next = get(d1.val, d2.val, 9, 3)
                    codeLength[5].next = get(d1.val, d2.val, 12, 3)
                    d1 = iram[di+5]
                    d2 = iram[di+6]
                    codeLength[11].next = get(d1.val, d2.val, 7, 3)
                    codeLength[4].next = get(d1.val, d2.val, 10, 3)
                    codeLength[12].next = get(d1.val, d2.val, 13, 3)
                    d1 = iram[di+7]
                    d2 = iram[di+8]
                    codeLength[3].next = get(d1.val, d2.val, 0, 3)
                    codeLength[13].next = get(d1.val, d2.val, 3, 3)
                    codeLength[2].next = get(d1.val, d2.val, 6, 3)
                    codeLength[14].next = get(d1.val, d2.val, 9, 3)
                    codeLength[1].next = get(d1.val, d2.val, 12, 3)
                    d1 = iram[di+8]
                    d2 = iram[di+9]
                    codeLength[15].next = get(d1.val, d2.val, 1, 3)

                    state.next = d_state.IDLE
                    o_done.next = True

                    """
                    if di <= isize:
                        d1 = iram[di]
                        oram[di].next = get(d1.val, d1.val, 0, 8)
                        adv(8)
                        do.next = di
                    else:
                        o_data.next = do
                    """

            elif i_mode == WRITE:
                iram[i_addr].next = i_data
                isize.next = i_addr
            elif i_mode == READ:
                o_data.next = oram[i_addr]
            elif i_mode == STARTC:
                raise Error("deflate compress not yet implemented")
            elif i_mode == STARTD:
                di.next = 6  # skip header
                dio.next = 0
                # decoding.next = True
                state.next = d_state.HEADER

    return logic


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[LBSIZE:]),
                Signal(intbv()[LBSIZE:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
