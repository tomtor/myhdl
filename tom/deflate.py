from math import log2

from myhdl import always, block, Signal, intbv, Error, ResetSignal, \
    instance, enum

IDLE, RESET, WRITE, READ, STARTC, STARTD = range(6)

BSIZE = 256
LBSIZE = log2(BSIZE)

d_state = enum('IDLE', 'HEADER', 'BL', 'HF1', 'HF2', 'HF3', 'HF4', 'DATA')


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
    MaxCodeLength = 15
    InstantMaxBit = 10
    EndOfBlock = 256

    codeLength = [Signal(intbv()[4:]) for _ in range(CodeLengths)]
    bitLengthCount = [Signal(intbv(0)[3:]) for _ in range(MaxCodeLength)]
    nextCode = [Signal(intbv(0)[10:]) for _ in range(MaxCodeLength)]

    Dictionary = [Signal(intbv()[16]) for _ in range(1024)]

    minBits = Signal(intbv()[4:])
    maxBits = Signal(intbv()[4:])
    instantMask = Signal(intbv()[MaxCodeLength:])

    code = Signal(intbv()[15:])

    cur_i = Signal(intbv()[5:])

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

    def rev_bits(b):
        r = (((b >> 14) & 0x1) << 0) | (((b >> 13) & 0x1) << 1) | \
            (((b >> 12) & 0x1) << 2) | (((b >> 11) & 0x1) << 3) | \
            (((b >> 10) & 0x1) << 4) | (((b >> 9) & 0x1) << 5) | \
            (((b >> 8) & 0x1) << 6) | (((b >> 7) & 0x1) << 7) | \
            (((b >> 6) & 0x1) << 8) | (((b >> 5) & 0x1) << 9) | \
            (((b >> 4) & 0x1) << 10) | (((b >> 3) & 0x1) << 11) | \
            (((b >> 2) & 0x1) << 12) | (((b >> 1) & 0x1) << 13) | \
            (((b >> 0) & 0x1) << 14)
        return r

    @always(clk.posedge)
    def logic():
        if not reset or i_mode == RESET:
            maxBits.next = 0
            minBits.next = CodeLengths
            code.next = 0
            for i in range(CodeLengths):
                codeLength[i].next = 0
            for i in range(MaxCodeLength):
                bitLengthCount[i].next = 0
                nextCode[i].next = 0
            for i in range(len(Dictionary)):
                Dictionary[i].next = 0
            state.next = d_state.IDLE
            di.next = 6
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
                    i = get(d1.val, 0, 1, 2)
                    method.next = i
                    print("method: %d" % i)
                    adv(3)
                    state.next = d_state.BL

                elif state == d_state.BL:

                    d1 = iram[di]

                    numLiterals.next = 257 + get(d1.val, 0, 0, 5)
                    d1 = iram[di+1]
                    d2 = iram[di+2]
                    numDistance.next = 1 + get(d1.val, d2.val, 0, 5)
                    numCodeLength.next = 4 + get(d1.val, d2.val, 5, 4)

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

                    di.next = di + 9

                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.HF1:
                    # get frequencies of each bit length and ignore 0's

                    if cur_i < CodeLengths:
                        j = codeLength[cur_i]
                        bitLengthCount[j].next = bitLengthCount[j] + 1
                        print(cur_i, j, bitLengthCount[j] + 1)
                        cur_i.next = cur_i + 1
                    else:
                        state.next = d_state.HF2
                        cur_i.next = 1

                elif state == d_state.HF2:
                    # shortest and longest codes

                    if cur_i < MaxCodeLength:
                        if bitLengthCount[cur_i] != 0:
                            if cur_i < minBits:
                                minBits.next = cur_i
                            if cur_i > maxBits:
                                maxBits.next = cur_i
                        cur_i.next = cur_i + 1
                    else:
                        print(minBits, maxBits)
                        t = InstantMaxBit
                        if t > int(maxBits):
                            t = int(maxBits)
                        instantMask.next = (1 << t) - 1
                        print((1 << t) - 1)
                        state.next = d_state.HF3
                        cur_i.next = minBits
                        print("HF3")

                elif state == d_state.HF3:
                    # find bit code for first element of each bitLength group

                    if cur_i <= maxBits:
                        ncode = (code + bitLengthCount[cur_i - 1]) << 1
                        code.next = ncode
                        nextCode[cur_i].next = ncode
                        print(cur_i, ncode)
                        cur_i.next = cur_i + 1
                    else:
                        state.next = d_state.HF4
                        cur_i.next = 0
                        print("HF4")

                elif state == d_state.HF4:
                    # create binary codes for each literal

                    if cur_i < CodeLengths:
                        bits = codeLength[cur_i]
                        if bits != 0:
                            canonical = nextCode[bits]
                            nextCode[bits].next = nextCode[bits] + 1
                            if bits > MaxCodeLength:
                                raise Error("too many bits")
                            reverse = rev_bits(canonical)
                            print(canonical, reverse)
                        cur_i.next = cur_i + 1
                    else:
                        o_done.next = True
                        state.next = d_state.IDLE
                    """
                    for i in range(len(codeLength)):
                        oram[i].next = codeLength[i]
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
                state.next = d_state.HEADER

    return logic


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[LBSIZE:]),
                Signal(intbv()[LBSIZE:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
