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

BSIZE = 2048
LBSIZE = log2(BSIZE)

d_state = enum('IDLE', 'HEADER', 'BL', 'READBL', 'REPEAT', 'DISTTREE',
               'HF1', 'HF2', 'HF3', 'HF4', 'STATIC', 'D_NEXT', 'D_INFLATE',
               'SPREAD', 'NEXT', 'INFLATE', 'COPY')

CodeLengthOrder = ( 16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15)

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
    final = Signal(bool(0))

    numLiterals = Signal(intbv()[9:])
    numDistance = Signal(intbv()[6:])
    numCodeLength = Signal(intbv()[9:])
    b_numCodeLength = Signal(intbv()[9:])

    CodeLengths = 19
    MaxCodeLength = 15
    InstantMaxBit = 10
    EndOfBlock = 256
    MaxBitLength = 288
    MaxToken = 285
    InvalidToken = 300

    CODEBITS = MaxCodeLength
    BITBITS = 9

    #codeLength = [Signal(intbv()[4:]) for _ in range(CodeLengths)]
    codeLength = [Signal(intbv()[4:]) for _ in range(290)]
    bitLengthCount = [Signal(intbv(0)[9:]) for _ in range(MaxCodeLength+1)]
    nextCode = [Signal(intbv(0)[CODEBITS:]) for _ in range(MaxCodeLength)]
    bitLength = [Signal(intbv()[4:]) for _ in range(MaxBitLength)]
    distanceLength = [Signal(intbv()[4:]) for _ in range(32)]

    leaves = [Signal(intbv()[CODEBITS + BITBITS:]) for _ in range(1024)]
    d_leaves = [Signal(intbv()[CODEBITS + BITBITS:]) for _ in range(32)]

    minBits = Signal(intbv()[5:])
    maxBits = Signal(intbv()[5:])
    d_maxBits = Signal(intbv()[5:])
    instantMaxBit = Signal(intbv()[InstantMaxBit:])
    d_instantMaxBit = Signal(intbv()[InstantMaxBit:])
    instantMask = Signal(intbv()[MaxCodeLength:])
    d_instantMask = Signal(intbv()[MaxCodeLength:])
    spread = Signal(intbv(0)[10:])
    step = Signal(intbv(0)[10:])

    static = Signal(bool(1))

    code = Signal(intbv()[15:])
    lastToken = Signal(intbv()[15:])
    howOften = Signal(intbv()[9:])
    # d_extraLength = Signal(intbv()[3:])
    # bitLengthSize = Signal(intbv()[9:])

    cur_i = Signal(intbv()[LBSIZE:])
    length = Signal(intbv()[LBSIZE:])
    offset = Signal(intbv()[LBSIZE:])
    compareTo = Signal(intbv()[9:])

    di = Signal(intbv()[LBSIZE:])
    dio = Signal(intbv()[3:])
    do = Signal(intbv()[LBSIZE:])

    b1 = Signal(intbv(0)[8:])
    b2 = Signal(intbv(0)[8:])
    b3 = Signal(intbv(0)[8:])
    b4 = Signal(intbv(0)[8:])
    nb = Signal(intbv(0)[3:])
    fill = Signal(bool(False))
    wtick = Signal(bool(False))

    @always(clk.posedge)
    def fill_buf():
        if not reset or not fill:
            nb.next = 0
        elif nb == 0:
            if di <= isize:
                b1.next = iram[di]
            nb.next = 1
        elif nb == 1:
            if di+1 <= isize:
                b2.next = iram[di+1]
            nb.next = 2
        elif nb == 2:
            if di+2 <= isize:
                b3.next = iram[di+2]
            nb.next = 3
        elif nb == 3:
            if di+3 <= isize:
                b4.next = iram[di+3]
            nb.next = 4

    """
    def get2(boffset, width):
        r = (((b2 << 8) | b1) >> (dio + boffset)) & ((1 << width) - 1)
        return r
    """

    def get4(boffset, width):
        if nb != 4:
            raise Error("NB")
        r = (((b4 << 24) | (b3 << 16) | (b2 << 8) | b1) >> \
             (dio + boffset)) & ((1 << width) - 1)
        return r

    def adv(width):
        nshift = ((dio + width) >> 3)
        if nshift >= nb:
            raise Error("Too many!")
        if nshift == 1:
            b1.next = b2
            b2.next = b3
            b3.next = b4
            nb.next = nb - 1
        elif nshift == 2:
            b1.next = b3
            b2.next = b4
            nb.next = nb - 2
        elif nshift == 3:
            raise Error("SHIFT3")
            # b1.next = b4
            # nb.next = nb - 3
        elif nshift == 4:
            raise Error("SHIFT4")
        else:
            pass

        dio.next = (dio + width) & 0x7  # % 8
        di.next = di + nshift

        if nshift:
            fill.next = False

    def rev_bits(b, nb):
        if b >= 1 << nb:
            #raise Error("too few bits")
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
        r= aleaf & ((1 << BITBITS) - 1)
        #if r == 1:
        #    raise Error("1 bit")
        return r

    def get_code(aleaf):
        return (aleaf >> BITBITS)  # & ((1 << CODEBITS) - 1)

    @always(clk.posedge)
    def logic():
        if not reset:
            state.next = d_state.IDLE
            o_done.next = False
            fill.next = False
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
                    """

                    if nb == 4:
                        if get4(0, 1):
                            print("final")
                            final.next = True
                        i = get4(1, 2)
                        method.next = i
                        print("method: %d" % i)
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
                        else:  # ii == 0:
                            state.next = d_state.COPY
                            di.next = 0
                            i = ((b3 << 8) | b2)
                            adv(21)
                            length.next = i
                            cur_i.next = 0
                            offset.next = 7

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
                    for i in range(len(bitLengthCount)):
                        bitLengthCount[i].next = 0
                    state.next = d_state.HF1

                elif state == d_state.BL:

                    if not fill:
                        fill.next = True
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
                        if numCodeLength < 19:
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
                            numCodeLength.next = 19
                            cur_i.next = 0
                            for i in range(len(bitLengthCount)):
                                bitLengthCount[i].next = 0
                            state.next = d_state.HF1

                elif state == d_state.READBL:

                    if not fill:
                        fill.next = True
                    elif nb < 4:
                        pass
                    elif numCodeLength == 0:
                        print("INIT READBL")
                        lastToken.next = 0
                        howOften.next = 0
                        # cur_i.next = 0
                    else:
                        print("READBL")

                    if nb < 4:
                        pass
                    elif numCodeLength < numLiterals + numDistance:
                        print(numLiterals + numDistance, numCodeLength, howOften, code, di)
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

                        # Fix this to be convertable:
                        for i in range(numLiterals, len(codeLength)): # MaxBitLength):
                            codeLength[i].next = 0

                        # raise Error("DO BL!")
                        method.next = 3  # Start building bit tree
                        cur_i.next = 0
                        for i in range(len(bitLengthCount)):
                            bitLengthCount[i].next = 0
                        state.next = d_state.HF1

                        # init HF1
                        maxBits.next = 0
                        minBits.next = CodeLengths
                        code.next = 0
                        for i in range(len(bitLengthCount)):
                            bitLengthCount[i].next = 0
                        for i in range(len(nextCode)):
                            nextCode[i].next = 0

                elif state == d_state.DISTTREE:

                    print("DISTTREE")
                    for i in range(numDistance):
                        codeLength[i].next = distanceLength[i]
                        print(i, distanceLength[i])
                    for i in range(numDistance, len(codeLength)):
                        codeLength[i].next = 0
                    for i in range(len(nextCode)):
                        nextCode[i].next = 0
                    numCodeLength.next = 32 # numDistance # 32
                    method.next = 4  # Start building dist tree
                    d_maxBits.next = 0
                    #d_instantMaxBit.next = 0
                    #d_instantMask.next = 0
                    minBits.next = CodeLengths
                    for i in range(len(bitLengthCount)):
                        bitLengthCount[i].next = 0
                    cur_i.next = 0
                    state.next = d_state.HF1

                elif state == d_state.REPEAT:

                    print("HOWOFTEN: ", howOften)
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
                        if method <= 2:
                            maxBits.next = 0
                        elif method == 4:
                            d_maxBits.next = 0
                        minBits.next = CodeLengths

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
                            print(cur_i, bits, canonical, reverse)
                            if method == 4:
                                d_leaves[reverse].next = makeLeaf(cur_i, bits)
                                if bits <= d_instantMaxBit:
                                    if reverse + (1 << bits) <= d_instantMask:
                                        step.next = 1 << bits
                                        spread.next =  reverse + (1 << bits)
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
                                        spread.next =  reverse + (1 << bits)
                                        state.next = d_state.SPREAD
                                    else:
                                        cur_i.next = cur_i + 1
                                else:
                                    cur_i.next = cur_i + 1
                        else:
                            cur_i.next = cur_i + 1
                    else:
                        if method == 3:
                            state.next = d_state.DISTTREE
                        elif method == 4:
                            print("DEFLATE m2!")
                            state.next = d_state.NEXT
                            #state.next = d_state.INFLATE
                        elif method == 2:
                            numCodeLength.next = 0
                            #state.next = d_state.READBL
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

                    if not fill:
                        fill.next = True
                    elif nb < 4:
                        pass
                    elif cur_i == 0:
                        print("INIT:", di, dio, instantMaxBit, maxBits)
                        if instantMaxBit <= maxBits:
                            compareTo.next = get4(0, maxBits)
                            cur_i.next = instantMaxBit
                        else:
                            print("FAIL instantMaxBit <= maxBits")
                            raise Error("FAIL instantMaxBit <= maxBits")
                    elif cur_i <= maxBits:
                        print("NEXT:", cur_i)
                        mask = (1 << cur_i) - 1
                        leaf = leaves[compareTo & mask]
                        if get_bits(leaf) <= cur_i:
                            if get_bits(leaf) == 0:
                                raise Error("0 bits")
                            adv(get_bits(leaf))
                            if get_code(leaf) == 0:
                                print("leaf 0")
                                #raise Error("bad code")
                            code.next = get_code(leaf)
                            print("ADV:", di, dio, compareTo, get_bits(leaf),
                                  get_code(leaf))
                            if method == 2:
                                #numCodeLength.next = 0
                                state.next = d_state.READBL
                            else:
                                # raise Error("DONE")
                                state.next = d_state.INFLATE
                        else:
                            print("FAIL get_bits(leaf) <= cur_i")
                            raise Error("?")
                    else:
                        print("no next token")
                        raise Error("no next token")

                elif state == d_state.D_NEXT:

                    if not fill:
                        fill.next = True
                    elif nb < 4:
                        pass
                    elif cur_i == 0:
                        print("D_INIT:", di, dio, d_instantMaxBit, d_maxBits)
                        if d_instantMaxBit <= d_maxBits:
                            token = code - 257
                            print("token: ", token)
                            extraLength = ExtraLengthBits[token]
                            print("extra length bits:", extraLength)
                            compareTo.next = get4(extraLength, d_maxBits)
                            cur_i.next = d_instantMaxBit
                        else:
                            raise Error("???")

                    elif cur_i <= d_maxBits:
                        mask = (1 << cur_i) - 1
                        leaf = d_leaves[compareTo & mask]
                        print(cur_i, compareTo, mask, leaf, d_maxBits)
                        if get_bits(leaf) <= cur_i:
                            if get_bits(leaf) == 0:
                                raise Error("0 bits")
                            token = code - 257
                            print("E2:", token)
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
                            distance += get4(extraLength + get_bits(leaf), moreBits)
                            # print("distance more:", distance)
                            adv(moreBits + extraLength + get_bits(leaf))
                            # print("advance:", moreBits + extraLength + get_bits(leaf))
                            print("offset:", do - distance)
                            offset.next = do - distance
                            length.next = tlength
                            state.next = d_state.COPY
                        else:
                            raise Error("?")
                    else:
                        raise Error("no next token")

                elif state == d_state.INFLATE:

                        if not fill:
                            fill.next = True
                        elif nb < 4: # nb <= 2 or (nb == 3 and dio > 1):
                            print("EXTRA FETCH", nb, dio)
                            pass  # fetch more bytes
                        elif di > isize:
                            state.next = d_state.IDLE
                            o_done.next = True
                            print("NO EOF ", di)
                            raise Error("NO EOF!")
                        elif code == EndOfBlock:
                            print("EOF:", di, do)
                            o_done.next = True
                            # o_data.next = do
                            state.next = d_state.IDLE
                        else:
                            if code < EndOfBlock:
                                print("B:", code, di)
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
                                    moreBits = ExtraDistanceBits[distanceCode >> 1]
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

                    if not fill:
                        fill.next = True
                    elif nb < 4:
                        pass
                    elif cur_i < length:
                        if method == 0:
                            oram[do].next = b4
                            adv(8)
                        else:
                            oram[do].next = oram[offset + cur_i]
                        cur_i.next = cur_i + 1
                        o_data.next = do + 1
                        do.next = do + 1
                    else:
                        print("LENGTH: ", length)
                        if method == 0:
                            o_done.next = True
                            state.next = d_state.IDLE
                        else:
                            cur_i.next = 0
                            state.next = d_state.NEXT

            elif i_mode == WRITE:

                iram[i_addr].next = i_data
                isize.next = i_addr

            elif i_mode == READ:

                o_data.next = oram[i_addr]

            elif i_mode == STARTC:

                o_done.next = False
                raise Error("deflate compress not yet implemented")

            elif i_mode == STARTD:

                o_done.next = False
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
                fill.next = True
                dio.next = 0
                do.next = 0
                state.next = d_state.HEADER

    return logic, fill_buf


if __name__ == "__main__":
    d = deflate(Signal(intbv()[3:]), Signal(bool(0)),
                Signal(intbv()[8:]), Signal(intbv()[LBSIZE:]),
                Signal(intbv()[LBSIZE:]),
                Signal(bool(0)), ResetSignal(1, 0, True))
    d.convert()
