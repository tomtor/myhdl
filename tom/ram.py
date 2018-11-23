@block
def ram(dout, din, addr, we, en, clk):

    """ Ram memory

    Ports:
    dout -- data out
    din -- data in
    addr -- address bus
    we -- write enable: write if 1, read otherwise
    en -- interface enable: enabled if 1
    clk -- clock input

    """

    bram = [Signal(intbv()[8:]) for _ in range(block_size)]

    @always(clk.posedge)
    def access():
        if en:
            if we:
                bram[addr.val] = din.val
            else:
                dout.next = bram[addr.val]

    return access

