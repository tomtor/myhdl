module init();
initial begin
	$dumpfile("test.vcd");
	$dumpvars(0,test_deflate_bench);
end
endmodule
