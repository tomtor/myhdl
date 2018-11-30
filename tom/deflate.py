"""
MyHDL FPGA Deflate (de)compressor, see RFC1951 and https://zlib.net

Copyright 2018 by Tom Vijlbrief

See: https://github.com/tomtor

This MyHDL FPGA implementation is partially inspired by the C++ implementation
from https://create.stephan-brumme.com/deflate-decoder

"""

from math import log2

from myhdl import always, block, Signal, intbv, Error, ResetSignal, \
    instance, enum

IDLE, RESET, WRITE, READ, STARTC, STARTD = range(6)

BSIZE = 256
LBSIZE = log2(BSIZE)

d_state = enum('IDLE', 'HEADER', 'BL', 'HF1', 'HF2', 'HF3', 'HF4', 'STATIC',
               'SPREAD', 'NEXT', 'INFLATE')

CopyLength = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35,
              43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258 )

ExtraLengthBits = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2,
                   3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0)

CopyDistance = (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193,
                257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193,
                12289, 16385, 24577)

ExtraDistanceBits = (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13)


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
    numCodeLength = Signal(intbv()[9:])

    CodeLengths = 19
    MaxCodeLength = 15
    InstantMaxBit = 10
    EndOfBlock = 256

    #codeLength = [Signal(intbv()[4:]) for _ in range(CodeLengths)]
    codeLength = [Signal(intbv()[4:]) for _ in range(288)]
    bitLengthCount = [Signal(intbv(0)[8:]) for _ in range(MaxCodeLength)]

    # Max bits is 10:
    CODEBITS = 10
    BITBITS = 6

    nextCode = [Signal(intbv(0)[CODEBITS:]) for _ in range(MaxCodeLength)]

    leaves = [Signal(intbv()[CODEBITS + BITBITS:]) for _ in range(1024)]

    minBits = Signal(intbv()[5:])
    maxBits = Signal(intbv()[5:])
    instantMaxBit = Signal(intbv()[InstantMaxBit:])
    instantMask = Signal(intbv()[MaxCodeLength:])
    spread = Signal(intbv(0)[10:])
    step = Signal(intbv(0)[10:])

    empty = Signal(bool(1))

    code = Signal(intbv()[15:])

    cur_i = Signal(intbv()[9:])
    compareTo = Signal(intbv()[9:])

    di = Signal(intbv()[LBSIZE:])
    dio = Signal(intbv()[3:])
    do = Signal(intbv()[LBSIZE:])

    def get(d1, d2, offset, width):
        """
        print("d:%s %s offset: %d dio:%d w:%d"
              % (hex(d1), hex(d2), offset, dio, width))
              """
        # r = ((((d1 << 8) | d2) << (dio + offset)) & 0xFFFF) >> (16 - width)
        r = (((d2 << 8) | d1) >> (dio + offset)) & ((1 << width) - 1)
        return r

    def adv(width):
        if dio + width > 7:
            di.next = di + 1
        dio.next = (dio + width) % 8

    def rev_bits(b, nb):
        if b >= 1 << nb:
            raise Error("too few bits")
        """
        r = (((b >> 14) & 0x1) << 0) | (((b >> 13) & 0x1) << 1) | \
            (((b >> 12) & 0x1) << 2) | (((b >> 11) & 0x1) << 3) | \
            (((b >> 10) & 0x1) << 4) | (((b >> 9) & 0x1) << 5) | \
            (((b >> 8) & 0x1) << 6) | (((b >> 7) & 0x1) << 7) | \
            (((b >> 6) & 0x1) << 8) | (((b >> 5) & 0x1) << 9) | \
            (((b >> 4) & 0x1) << 10) | (((b >> 3) & 0x1) << 11) | \
            (((b >> 2) & 0x1) << 12) | (((b >> 1) & 0x1) << 13) | \
            (((b >> 0) & 0x1) << 14)
        r >>= (15 - nb)
        """
        r = 0
        x = b & 0xFFFF
        for _ in range(0, nb):
            r <<= 1
            r |= (x & 1)
            x >>= 1
        return r

    def makeLeaf(code, bits):
        if code >= 1 << CODEBITS:
            raise Error("code too big")
        if bits >= 1 << BITBITS:
            raise Error("bits too big")
        return (cur_i << BITBITS) | bits

    def get_bits(leaf):
        return leaf & ((1 << BITBITS) - 1)

    def get_code(leaf):
        return leaf >> BITBITS

    @always(clk.posedge)
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
                    if get(d1.val, 0, 0, 1):
                        print("final")
                        final.next = True
                    i = get(d1.val, 0, 1, 2)
                    method.next = i
                    print("method: %d" % i)
                    if method == 2:
                        state.next = d_state.BL
                        """
                        print("Code lengths")
                        for i in range(2,11):
                            print(iram[i])
                        print("End Code lengths")
                        """
                    elif method == 1:
                        dio.next = 3
                        state.next = d_state.STATIC

                elif state == d_state.STATIC:

                    for i in range(0, 144):
                        codeLength[i].next = 8;
                    for i in range(144, 256):
                        codeLength[i].next = 9;
                    for i in range(256, 280):
                        codeLength[i].next = 7;
                    for i in range(280, 288):
                        codeLength[i].next = 8;
                    numCodeLength.next = 288
                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.BL:

                    d1 = iram[di]

                    numLiterals.next = 257 + get(d1.val, 0, 3, 5)
                    d1 = iram[di+1]
                    d2 = iram[di+2]
                    numDistance.next = 1 + get(d1.val, d2.val, 0, 5)
                    numCodeLength.next = 4 + get(d1.val, d2.val, 5, 4)
                    print("NCL")
                    print(int(4 + get(d1.val, d2.val, 5, 4)))

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
                    codeLength[15].next = get(d1.val, d2.val, 7, 3)

                    di.next = di + 9
                    dio.next = 2

                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.HF1:
                    # get frequencies of each bit length and ignore 0's

                    if cur_i < numCodeLength:
                        j = codeLength[cur_i]
                        bitLengthCount[j].next = bitLengthCount[j] + 1
                        print(cur_i, j, bitLengthCount[j] + 1)
                        cur_i.next = cur_i + 1
                    else:
                        bitLengthCount[0].next = 0
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
                        instantMaxBit.next = t
                        instantMask.next = (1 << t) - 1
                        print((1 << t) - 1)
                        state.next = d_state.HF3
                        cur_i.next = minBits
                        print("HF3")

                elif state == d_state.HF3:
                    # find bit code for first element of each bitLength group

                    if cur_i <= maxBits:
                        ncode = ((code + bitLengthCount[cur_i - 1]) << 1)
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

                    if cur_i < numCodeLength:
                        bits = codeLength[cur_i]
                        if bits != 0:
                            canonical = nextCode[bits]
                            nextCode[bits].next = nextCode[bits] + 1
                            if bits > MaxCodeLength:
                                raise Error("too many bits")
                            reverse = rev_bits(canonical, bits)
                            print(cur_i, bits, canonical, reverse)
                            leaves[reverse].next = makeLeaf(cur_i, bits)
                            if bits <= instantMaxBit:
                                if reverse + (1 << bits) <= instantMask:
                                    step.next = 1 << bits
                                    spread.next =  reverse + (1 << bits)
                                    state.next = d_state.SPREAD
                                else:
                                    cur_i.next = cur_i + 1
                            else:
                                cur_i.next = cur_i + 1
                        else:
                            cur_i.next = cur_i + 1
                    else:
                        state.next = d_state.NEXT
                        cur_i.next = 0

                elif state == d_state.SPREAD:

                    leaves[spread].next = makeLeaf(cur_i, codeLength[cur_i])
                    # print("SPREAD:", spread, step, instantMask, instantMaxBit)
                    if spread > instantMask - step:
                        cur_i.next = cur_i + 1
                        state.next = d_state.HF4
                    else:
                        spread.next = spread + step

                elif state == d_state.NEXT:

                    if cur_i == 0:
                        print("INIT:", di, dio)
                        if instantMaxBit <= maxBits:
                            d1 = iram[di]
                            d2 = iram[di+1]
                            compareTo.next = get(d1.val, d2.val, 0, maxBits)
                            cur_i.next  = instantMaxBit
                    elif cur_i <= maxBits:
                        mask = (1 << cur_i) - 1
                        leaf = leaves[compareTo & mask]
                        if get_bits(leaf) <= cur_i:
                            adv(get_bits(leaf))
                            code.next = get_code(leaf)
                            print("ADV:", di, dio, compareTo, get_bits(leaf))
                            state.next = d_state.INFLATE
                    else:
                        raise Error("no next token")

                elif state == d_state.INFLATE:

                        if code == EndOfBlock:
                            print("EOF:", di, do)
                            o_done.next = True
                            o_data.next = do
                            state.next = d_state.IDLE
                        else:
                            if code < EndOfBlock:
                                print("B:", code)
                                oram[do].next = code
                                do.next = do + 1
                            elif code == 300:
                                raise Error("invalid token")
                            else:
                                token = code - 257
                                length = CopyLength[token]
                                extraLength = ExtraLengthBits[token]
                                d1 = iram[di]
                                d2 = iram[di+1]
                                length +=  get(d1.val, d2.val, 0, extraLength)
                                print("E:", token)
                                if empty:
                                    distanceCode = 1
                            cur_i.next = 0
                            state.next = d_state.NEXT

            elif i_mode == WRITE:

                iram[i_addr].next = i_data
                isize.next = i_addr

            elif i_mode == READ:

                o_data.next = oram[i_addr]

            elif i_mode == STARTC:

                raise Error("deflate compress not yet implemented")

            elif i_mode == STARTD:

                maxBits.next = 0
                minBits.next = CodeLengths
                code.next = 0
                for i in range(len(codeLength)):
                    codeLength[i].next = 0
                for i in range(MaxCodeLength):
                    bitLengthCount[i].next = 0
                    nextCode[i].next = 0
                for i in range(len(leaves)):
                    leaves[i].next = 0
                di.next = 2
                dio.next = 0
                state.next = d_state.HEADER

    return logic


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[LBSIZE:]),
                Signal(intbv()[LBSIZE:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
