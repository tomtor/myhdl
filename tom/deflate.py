"""
MyHDL FPGA Deflate (de)compressor, see RFC1951 and https://zlib.net

Copyright 2018 by Tom Vijlbrief

See: https://github.com/tomtor

This MyHDL FPGA implementation is partially inspired by the C++ implementation
from https://create.stephan-brumme.com/deflate-decoder

"""

from math import log2

from myhdl import always, block, Signal, intbv, Error, ResetSignal, \
    enum, always_seq, always_comb

IDLE, RESET, WRITE, READ, STARTC, STARTD = range(6)

BSIZE = 2048
LBSIZE = log2(BSIZE)

d_state = enum('IDLE', 'HEADER', 'BL', 'READBL', 'REPEAT', 'DISTTREE', 'INIT3',
               'HF1', 'HF1INIT', 'HF2', 'HF3', 'HF4', 'STATIC', 'D_NEXT',
               'D_INFLATE', 'SPREAD', 'NEXT', 'INFLATE', 'COPY', 'CSTATIC',
               encoding='one_hot')

CodeLengthOrder = (16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14,
                   1, 15)

CopyLength = (3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35,
              43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258)

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
    method = Signal(intbv()[3:])
    final = Signal(bool())
    do_compress = Signal(bool())

    numLiterals = Signal(intbv()[9:])
    numDistance = Signal(intbv()[6:])
    numCodeLength = Signal(intbv()[9:])
    b_numCodeLength = Signal(intbv()[9:])

    CodeLengths = 19
    MaxCodeLength = 15
    InstantMaxBit = 10
    EndOfBlock = 256
    MaxBitLength = 288
    # MaxToken = 285
    InvalidToken = 300

    CODEBITS = MaxCodeLength
    BITBITS = 9

    codeLength = [Signal(intbv()[4:]) for _ in range(MaxBitLength+32)]
    bitLengthCount = [Signal(intbv(0)[9:]) for _ in range(MaxCodeLength+1)]
    nextCode = [Signal(intbv()[CODEBITS:]) for _ in range(MaxCodeLength)]
    distanceLength = [Signal(intbv()[4:]) for _ in range(32)]

    leaves = [Signal(intbv()[CODEBITS + BITBITS:]) for _ in range(512)]
    d_leaves = [Signal(intbv()[CODEBITS + BITBITS:]) for _ in range(64)]
    leaf = Signal(intbv()[CODEBITS + BITBITS:])

    minBits = Signal(intbv()[5:])
    maxBits = Signal(intbv()[5:])
    d_maxBits = Signal(intbv()[5:])
    instantMaxBit = Signal(intbv()[InstantMaxBit:])
    d_instantMaxBit = Signal(intbv()[InstantMaxBit:])
    instantMask = Signal(intbv()[MaxCodeLength:])
    d_instantMask = Signal(intbv()[MaxCodeLength:])
    spread = Signal(intbv()[10:])
    step = Signal(intbv()[10:])

    static = Signal(bool())

    code = Signal(intbv()[15:])
    lastToken = Signal(intbv()[15:])
    howOften = Signal(intbv()[9:])

    cur_i = Signal(intbv()[LBSIZE:])
    length = Signal(intbv()[LBSIZE:])
    offset = Signal(intbv()[LBSIZE:])
    compareTo = Signal(intbv()[9:])

    di = Signal(intbv()[LBSIZE:])
    old_di = Signal(intbv()[LBSIZE:])
    dio = Signal(intbv()[3:])
    do = Signal(intbv()[LBSIZE:])
    doo = Signal(intbv()[3:])

    b1 = Signal(intbv()[8:])
    b2 = Signal(intbv()[8:])
    b3 = Signal(intbv()[8:])
    b4 = Signal(intbv()[8:])
    nb = Signal(intbv()[3:])
    filled = Signal(bool())
    wait_data = Signal(bool())

    ob1 = Signal(intbv()[8:])
    putbyte = Signal(intbv()[8:])
    flush = Signal(bool(0))

    """
    wtick = Signal(bool())
    """
    nextb = Signal(intbv()[8:])


    @always_seq(clk.posedge, reset)
    def fill_buf():
        if not reset or wait_data:
            nb.next = 0
            old_di.next = 0
            b1.next = 0
            b2.next = 0
            b3.next = 0
            b4.next = 0
        elif not filled and nb == 4:
            delta = di - old_di
            if delta == 1:
                print("delta == 1")
                b1.next = b2
                b2.next = b3
                b3.next = b4
                b4.next = iram[di+3]
            elif delta == 2:
                b1.next = b3
                b2.next = b4
                b3.next = iram[di+2]
            elif delta == 3:
                b1.next = b4
                b2.next = iram[di+1]
            elif delta == 4:
                b1.next = iram[di]
            else:
                delta = 1  # Adjust delta for next line calculation
            nb.next = nb - delta + 1  # + 1 because we read 1 byte
        elif not filled or nb == 0:
            print("nb.next = 1")
            b1.next = iram[di]
            nb.next = 1
        elif not filled or nb == 1:
            b2.next = iram[di+1]
            nb.next = 2
        elif not filled or nb == 2:
            b3.next = iram[di+2]
            nb.next = 3
        elif not filled or nb == 3:
            b4.next = iram[di+3]
            nb.next = 4
        else:
            pass
        old_di.next = di

    def get4(boffset, width):
        if nb != 4:
            print("----NB----")
            raise Error("NB")
        # print(b1,b2,b3,b4)
        r = (((b4 << 24) | (b3 << 16) | (b2 << 8) | b1) >>
             (dio + boffset)) & ((1 << width) - 1)
        return r

    def adv(width):
        nshift = ((dio + width) >> 3)
        print("nshift: ", nshift)

        dio.next = (dio + width) & 0x7
        di.next = di + nshift

        if nshift != 0:
            filled.next = False

    def put(d, width):
        if width > 9:
            raise Error("width > 9")
        print("put:", d, width, do, doo)
        pshift = ((doo + width) >> 3)
        print("pshift: ", pshift)
        if pshift:
            putbyte.next = ((ob1 << width) | d) & 0xFF
            o_data.next = do
            do.next = do + 1
            carry = width - (8 - doo)
            ob1.next = d >> carry
        else:
            if d >= (1 << width):
                raise Error("put too wide")
            ob1.next = (ob1 << width) | d
        do.next = do + pshift
        doo_next = (doo + width) & 0x7
        flush.next = (doo_next == 0) 
        doo.next= doo_next

    def do_flush():
        print("FLUSH")
        flush.next = False
        ob1.next = 0
        o_data.next = do
        do.next = do + 1

    def rev_bits(b, nb):
        if b >= 1 << nb:
            raise Error("too few bits")
            print("too few bits")
        r = (((b >> 14) & 0x1) << 0) | (((b >> 13) & 0x1) << 1) | \
            (((b >> 12) & 0x1) << 2) | (((b >> 11) & 0x1) << 3) | \
            (((b >> 10) & 0x1) << 4) | (((b >> 9) & 0x1) << 5) | \
            (((b >> 8) & 0x1) << 6) | (((b >> 7) & 0x1) << 7) | \
            (((b >> 6) & 0x1) << 8) | (((b >> 5) & 0x1) << 9) | \
            (((b >> 4) & 0x1) << 10) | (((b >> 3) & 0x1) << 11) | \
            (((b >> 2) & 0x1) << 12) | (((b >> 1) & 0x1) << 13) | \
            (((b >> 0) & 0x1) << 14)
        r >>= (15 - nb)
        return r

    def makeLeaf(lcode, lbits):
        if lcode >= 1 << CODEBITS:
            raise Error("code too big")
        if lbits >= 1 << BITBITS:
            raise Error("bits too big")
        return (lcode << BITBITS) | lbits

    def get_bits(aleaf):
        r = aleaf & ((1 << BITBITS) - 1)
        return r

    def get_code(aleaf):
        return (aleaf >> BITBITS)  # & ((1 << CODEBITS) - 1)

    @always(clk.posedge)
    def logic():
        if not reset:
            print("DEFLATE RESET")
            state.next = d_state.IDLE
            o_done.next = False
            #filled.next = False
            wait_data.next = True
        else:
            if i_mode == IDLE:

                if state == d_state.IDLE:

                    wait_data.next = True

                elif state == d_state.HEADER:

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
                    """

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    else:
                        if get4(0, 1):
                            print("final")
                            final.next = True
                        i = get4(1, 2)
                        method.next = i
                        print("method: %d" % i)
                        print(di, dio, nb, b1, b2, b3, b4, i)
                        if i == 2:
                            state.next = d_state.BL
                            numCodeLength.next = 0
                            numLiterals.next = 0
                            static.next = False
                            adv(3)
                        elif i == 1:
                            static.next = True
                            state.next = d_state.STATIC
                            adv(3)
                        elif i == 0:
                            state.next = d_state.COPY
                            skip = 8 - dio
                            if skip <= 2:
                                skip = 16 - dio
                            i = get4(skip, 16)
                            adv(skip + 16)
                            length.next = i
                            cur_i.next = 0
                            offset.next = 7
                        else:
                            print("Bad method")
                            raise Error("Bad method")

                elif state == d_state.CSTATIC:

                    print("CSTATIC", cur_i, do, isize)
                    if cur_i == 0:
                        flush.next = False
                        ob1.next = 0
                        oram[0].next = 0x78
                    elif cur_i == 1:
                        oram[1].next = 0x9c
                        do.next = 2
                    elif cur_i == 2:
                        put(0x3, 3)
                    elif flush:
                        oram[do].next = ob1
                        do_flush()
                    elif cur_i - 3 > isize:
                        if cur_i - 3 == isize + 1:
                            print("Put EOF")
                            i = EndOfBlock
                            outlen = codeLength[i]
                            codeoffset = i - nextCode[outlen]
                            theleaf = leaves[nextCode[outlen] + codeoffset]
                            outbits = get_code(theleaf)
                            print("EOF BITS:", i, outlen, outbits)
                            put(outbits, outlen)
                        oram[do].next = ob1
                        o_done.next = True
                        o_data.next = do + 1
                        if not flush:
                            state.next = d_state.IDLE
                        else:
                            print("FLUSH EOF")
                    else:
                        bdata = iram[cur_i - 3]
                        outlen = codeLength[bdata]
                        codeoffset = bdata - nextCode[outlen]
                        theleaf = leaves[nextCode[outlen] + codeoffset]
                        outbits = get_code(theleaf)
                        print("BITS:", bdata, outlen, outbits)
                        put(outbits, outlen)
                        oram[do].next = ob1
                    cur_i.next = cur_i + 1

                elif state == d_state.STATIC:

                    for i in range(0, 144):
                        codeLength[i].next = 8
                    for i in range(144, 256):
                        codeLength[i].next = 9
                    for i in range(256, 280):
                        codeLength[i].next = 7
                    for i in range(280, 288):
                        codeLength[i].next = 8
                    numCodeLength.next = 288
                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.BL:

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif numLiterals == 0:
                        numLiterals.next = 257 + get4(0, 5)
                        print("NL:", 257 + get4(0, 5))
                        numDistance.next = 1 + get4(5, 5)
                        print("ND:", 1 + get4(5, 5))
                        b_numCodeLength.next = 4 + get4(10, 4)
                        print("NCL:", 4 + get4(10, 4))
                        numCodeLength.next = 0
                        adv(14)
                    else:
                        if numCodeLength < CodeLengths:
                            i = CodeLengthOrder[numCodeLength]
                            print("CLI: ", i)
                            if numCodeLength < b_numCodeLength:
                                codeLength[i].next = get4(0, 3)
                                adv(3)
                            else:
                                print("SKIP")
                                codeLength[i].next = 0
                            numCodeLength.next = numCodeLength + 1
                        else:
                            numCodeLength.next = CodeLengths
                            cur_i.next = 0
                            state.next = d_state.HF1

                elif state == d_state.READBL:

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif numCodeLength < numLiterals + numDistance:
                        print(numLiterals + numDistance, numCodeLength,
                              howOften, code, di)
                        i = 0
                        if code < 16:
                            howOften.next = 1
                            lastToken.next = code
                        elif code == 16:
                            howOften.next = 3 + get4(0, 2)
                            i = 2
                        elif code == 17:
                            howOften.next = 3 + get4(0, 3)
                            lastToken.next = 0
                            i = 3
                        elif code == 18:
                            howOften.next = 11 + get4(0, 7)
                            lastToken.next = 0
                            i = 7
                        else:
                            raise Error("Invalid data")

                        print(numCodeLength, howOften, code, di, i)
                        if i != 0:
                            adv(i)

                        state.next = d_state.REPEAT
                    else:
                        print("FILL UP")

                        for i in range(32):
                            dbl = 0
                            if i + numLiterals < numCodeLength:
                                dbl = int(codeLength[i + numLiterals])
                            print("dbl:", dbl)
                            distanceLength[i].next = dbl

                        print(numCodeLength, numLiterals, MaxBitLength)

                        cur_i.next = numLiterals
                        state.next = d_state.INIT3

                elif state == d_state.INIT3:

                        if cur_i < MaxBitLength:
                            codeLength[cur_i].next = 0
                            cur_i.next = cur_i + 1
                        else:
                            numCodeLength.next = MaxBitLength
                            method.next = 3  # Start building bit tree
                            cur_i.next = 0
                            state.next = d_state.HF1

                elif state == d_state.DISTTREE:

                    print("DISTTREE")
                    for i in range(32):
                        codeLength[i].next = distanceLength[i]
                        print(i, distanceLength[i])
                    numCodeLength.next = 32
                    method.next = 4  # Start building dist tree
                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.REPEAT:

                    print("HOWOFTEN: ", numCodeLength, howOften)
                    if howOften != 0:
                        codeLength[numCodeLength].next = lastToken
                        howOften.next = howOften - 1
                        numCodeLength.next = numCodeLength + 1
                    elif numCodeLength < numLiterals + numDistance:
                        cur_i.next = 0
                        state.next = d_state.NEXT
                    else:
                        state.next = d_state.READBL

                elif state == d_state.HF1:

                    if cur_i < len(bitLengthCount):
                        bitLengthCount[cur_i].next = 0
                    if cur_i < len(d_leaves):
                        d_leaves[cur_i].next = 0
                    if method != 4 and cur_i < len(leaves):
                        leaves[cur_i].next = 0
                    limit = len(leaves)
                    if method == 4:
                        limit = len(d_leaves)
                    if cur_i < limit:
                        cur_i.next = cur_i + 1
                        """
                    if cur_i < len(bitLengthCount):
                        bitLengthCount[cur_i].next = 0
                        cur_i.next = cur_i + 1
                    """
                    else:
                        print("DID HF1 INIT")
                        cur_i.next = 0
                        state.next = d_state.HF1INIT

                elif state == d_state.HF1INIT:
                    # get frequencies of each bit length and ignore 0's

                    print("HF1")
                    if cur_i < numCodeLength:
                        j = codeLength[cur_i]
                        bitLengthCount[j].next = bitLengthCount[j] + 1
                        print(cur_i, j, bitLengthCount[j] + 1)
                        cur_i.next = cur_i + 1
                    else:
                        bitLengthCount[0].next = 0
                        state.next = d_state.HF2
                        cur_i.next = 1
                        if method == 4:
                            d_maxBits.next = 0
                        else:
                            maxBits.next = 0
                        minBits.next = MaxCodeLength

                elif state == d_state.HF2:
                    # shortest and longest codes

                    print("HF2")
                    if cur_i <= MaxCodeLength:
                        if bitLengthCount[cur_i] != 0:
                            if cur_i < minBits:
                                minBits.next = cur_i
                            if method == 4:
                                if cur_i > d_maxBits:
                                    d_maxBits.next = cur_i
                            else:
                                if cur_i > maxBits:
                                    maxBits.next = cur_i
                        cur_i.next = cur_i + 1
                    else:
                        print(minBits, maxBits)
                        t = InstantMaxBit
                        if method == 4:
                            if t > int(d_maxBits):
                                t = int(d_maxBits)
                            d_instantMaxBit.next = t
                            d_instantMask.next = (1 << t) - 1
                        else:
                            if t > int(maxBits):
                                t = int(maxBits)
                            instantMaxBit.next = t
                            instantMask.next = (1 << t) - 1
                        print((1 << t) - 1)
                        state.next = d_state.HF3
                        cur_i.next = minBits
                        code.next = 0
                        for i in range(len(nextCode)):
                            nextCode[i].next = 0
                        print("to HF3")

                elif state == d_state.HF3:
                    # find bit code for first element of each bitLength group

                    print("HF3")
                    amb = maxBits
                    if method == 4:
                        amb = d_maxBits
                    if cur_i <= amb:
                        ncode = ((code + bitLengthCount[cur_i - 1]) << 1)
                        code.next = ncode
                        nextCode[cur_i].next = ncode
                        print(cur_i, ncode)
                        cur_i.next = cur_i + 1
                    else:
                        state.next = d_state.HF4
                        cur_i.next = 0
                        print("to HF4")

                elif state == d_state.HF4:
                    # create binary codes for each literal

                    if cur_i < numCodeLength:
                        bits = codeLength[cur_i]
                        if bits != 0:
                            canonical = nextCode[bits]
                            nextCode[bits].next = nextCode[bits] + 1
                            if bits > MaxCodeLength:
                                raise Error("too many bits: %d" % bits)
                            print(canonical, bits)
                            reverse = rev_bits(canonical, bits)
                            print("LEAF: ", cur_i, bits, reverse)
                            if method == 4:
                                d_leaves[reverse].next = makeLeaf(cur_i, bits)
                                if bits <= d_instantMaxBit:
                                    if reverse + (1 << bits) <= d_instantMask:
                                        step.next = 1 << bits
                                        spread.next = reverse + (1 << bits)
                                        state.next = d_state.SPREAD
                                    else:
                                        cur_i.next = cur_i + 1
                                else:
                                    cur_i.next = cur_i + 1
                            else:
                                leaves[reverse].next = makeLeaf(cur_i, bits)
                                if bits <= instantMaxBit:
                                    if reverse + (1 << bits) <= instantMask:
                                        step.next = 1 << bits
                                        spread.next = reverse + (1 << bits)
                                        state.next = d_state.SPREAD
                                    else:
                                        cur_i.next = cur_i + 1
                                else:
                                    cur_i.next = cur_i + 1
                        else:
                            cur_i.next = cur_i + 1
                    else:
                        if do_compress:
                            state.next = d_state.CSTATIC
                        elif method == 3:
                            state.next = d_state.DISTTREE
                        elif method == 4:
                            print("DEFLATE m2!")
                            state.next = d_state.NEXT
                        elif method == 2:
                            numCodeLength.next = 0
                            state.next = d_state.NEXT
                        else:
                            state.next = d_state.NEXT
                        cur_i.next = 0

                elif state == d_state.SPREAD:

                    if method == 4:
                        d_leaves[spread].next = makeLeaf(
                            cur_i, codeLength[cur_i])
                    else:
                        leaves[spread].next = makeLeaf(
                            cur_i, codeLength[cur_i])
                    print("SPREAD:", spread, step, instantMask, instantMaxBit)
                    aim = instantMask
                    if method == 4:
                        aim = d_instantMask
                    if spread > aim - step:
                        cur_i.next = cur_i + 1
                        state.next = d_state.HF4
                    else:
                        spread.next = spread + step

                elif state == d_state.NEXT:

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif cur_i == 0:
                        print("INIT:", di, dio, instantMaxBit, maxBits)
                        if instantMaxBit <= maxBits:
                            cto = get4(0, maxBits)
                            compareTo.next = cto
                            cur_i.next = instantMaxBit
                            mask = (1 << instantMaxBit) - 1
                            leaf.next = leaves[cto & mask]
                            print(cur_i, compareTo, mask, leaf, maxBits)
                        else:
                            print("FAIL instantMaxBit <= maxBits")
                            raise Error("FAIL instantMaxBit <= maxBits")
                    elif cur_i <= maxBits:
                        print("NEXT:", cur_i)
                        if get_bits(leaf) <= cur_i:
                            if get_bits(leaf) < 1:
                                print("< 1 bits: ")
                                raise Error("< 1 bits: ")
                            adv(get_bits(leaf))
                            if get_code(leaf) == 0:
                                print("leaf 0")
                            code.next = get_code(leaf)
                            print("ADV:", di, dio, compareTo, get_bits(leaf),
                                  get_code(leaf))
                            if method == 2:
                                state.next = d_state.READBL
                            else:
                                state.next = d_state.INFLATE
                        else:
                            print("FAIL get_bits(leaf) <= cur_i")
                            raise Error("?")
                    else:
                        print("no next token")
                        raise Error("no next token")

                elif state == d_state.D_NEXT:

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif cur_i == 0:
                        print("D_INIT:", di, dio, d_instantMaxBit, d_maxBits)
                        if d_instantMaxBit <= d_maxBits:
                            token = code - 257
                            print("token: ", token)
                            extraLength = ExtraLengthBits[token]
                            print("extra length bits:", extraLength)
                            cto = get4(extraLength, d_maxBits)
                            compareTo.next = cto
                            cur_i.next = d_instantMaxBit
                            mask = (1 << d_instantMaxBit) - 1
                            leaf.next = d_leaves[cto & mask]
                            print(cur_i, compareTo, mask, leaf, d_maxBits)
                        else:
                            raise Error("???")

                    elif cur_i <= d_maxBits:
                        if get_bits(leaf) <= cur_i:
                            if get_bits(leaf) == 0:
                                raise Error("0 bits")
                            token = code - 257
                            print("E2:", token, leaf)
                            tlength = CopyLength[token]
                            # print("tlength:", tlength)
                            extraLength = ExtraLengthBits[token]
                            # print("extra length bits:", extraLength)
                            tlength += get4(0, extraLength)
                            # print("extra length:", tlength)
                            distanceCode = get_code(leaf)
                            # print("distance code:", distanceCode)
                            distance = CopyDistance[distanceCode]
                            # print("distance:", distance)
                            moreBits = ExtraDistanceBits[distanceCode >> 1]
                            # print("more bits:", moreBits)
                            # print("bits:", get_bits(leaf))
                            mored = get4(extraLength + get_bits(leaf),
                                         moreBits)
                            # print("mored:", mored)
                            distance += mored
                            # print("distance more:", distance)
                            adv(moreBits + extraLength + get_bits(leaf))
                            # print("offset:", do - distance)
                            # print("FAIL?: ", di, dio, do, b1, b2, b3, b4)
                            offset.next = do - distance
                            length.next = tlength
                            cur_i.next = 0
                            state.next = d_state.COPY

                        else:
                            raise Error("?")
                    else:
                        raise Error("no next token")

                elif state == d_state.INFLATE:

                        if not filled:
                            filled.next = True
                        elif nb < 4:  # nb <= 2 or (nb == 3 and dio > 1):
                            # print("EXTRA FETCH", nb, dio)
                            pass  # fetch more bytes
                        elif di > isize:
                            state.next = d_state.IDLE
                            o_done.next = True
                            print("NO EOF ", di)
                            raise Error("NO EOF!")
                        elif code == EndOfBlock:
                            print("EOF:", di, do)
                            if not final:
                                state.next = d_state.HEADER
                            else:
                                o_done.next = True
                                state.next = d_state.IDLE
                        else:
                            if code < EndOfBlock:
                                print("B:", code, di, do)
                                oram[do].next = code
                                o_data.next = do + 1
                                do.next = do + 1
                                state.next = d_state.NEXT
                                # raise Error("DF!")
                            elif code == InvalidToken:
                                raise Error("invalid token")
                            else:
                                if static:
                                    token = code - 257
                                    print("E:", token)
                                    tlength = CopyLength[token]
                                    extraLength = ExtraLengthBits[token]
                                    tlength += get4(0, extraLength)
                                    t = get4(extraLength, 5)
                                    distanceCode = rev_bits(t, 5)
                                    distance = CopyDistance[distanceCode]
                                    moreBits = ExtraDistanceBits[distanceCode
                                                                 >> 1]
                                    distance += get4(extraLength + 5, moreBits)
                                    adv(extraLength + 5 + moreBits)
                                    offset.next = do - distance
                                    length.next = tlength
                                    state.next = d_state.COPY
                                else:
                                    # raise Error("TO DO")
                                    state.next = d_state.D_NEXT
                            cur_i.next = 0

                elif state == d_state.COPY:

                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif method != 0 and cur_i == 0:
                        nextb.next = oram[offset]
                        cur_i.next = 1
                        if length <= 1:
                            raise Error("length <= 1")
                    elif cur_i < length:
                        if method == 0:
                            oram[do].next = b3
                            adv(8)
                        else:
                            oram[do].next = nextb # oram[offset + cur_i]
                            nextb.next = oram[offset + cur_i]
                        cur_i.next = cur_i + 1
                        o_data.next = do + 1
                        do.next = do + 1
                    else:
                        if method != 0:
                            oram[do].next = nextb
                            do.next = do + 1
                        print("LENGTH: ", length)
                        if method == 0:
                            o_done.next = True
                            state.next = d_state.IDLE
                        else:
                            cur_i.next = 0
                            state.next = d_state.NEXT
                    """
                    if not filled:
                        filled.next = True
                    elif nb < 4:
                        pass
                    elif cur_i < length:
                        if method == 0:
                            oram[do].next = b3
                            adv(8)
                        else:
                            oram[do].next = oram[offset + cur_i]
                        cur_i.next = cur_i + 1
                        o_data.next = do + 1
                        do.next = do + 1
                    else:
                        print("LENGTH: ", length)
                        if method == 0:
                            if not final:
                                state.next = d_state.HEADER
                            else:
                                o_done.next = True
                                state.next = d_state.IDLE
                        else:
                            cur_i.next = 0
                            state.next = d_state.NEXT
                            """

            elif i_mode == WRITE:

                print("WRITE:", i_addr, i_data)
                iram[i_addr].next = i_data
                isize.next = i_addr

            elif i_mode == READ:

                o_data.next = oram[i_addr]

            elif i_mode == STARTC:

                print("STARTC")
                do_compress.next = True
                method.next = 1
                o_done.next = False
                di.next = 0
                dio.next = 0
                do.next = 0
                filled.next = True
                wait_data.next = False

                state.next = d_state.STATIC

            elif i_mode == STARTD:

                do_compress.next = False
                o_done.next = False
                """
                for i in range(len(leaves)):
                    leaves[i].next = 0
                for i in range(len(d_leaves)):
                    d_leaves[i].next = 0
                    """
                di.next = 2
                dio.next = 0
                do.next = 0
                filled.next = True
                wait_data.next = False
                state.next = d_state.HEADER

    return logic, fill_buf


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[LBSIZE:]),
                Signal(intbv()[LBSIZE:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
