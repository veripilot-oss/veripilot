`timescale 1ns / 1ps

module tb_fifo_flaky;
    reg clk;
    reg reset;
    reg [31:0] val;

    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    initial begin
        reset = 1;
        #20;
        reset = 0;
        #10;
        val = $urandom();
        // In Verilator, with seeds 1..5:
        // 4294967292 % 3 == 0 (seed 1 fails)
        // 4294967290 % 3 == 1 (seed 2 passes)
        // 4294967288 % 3 == 2 (seed 3 passes)
        // 4294967286 % 3 == 0 (seed 4 fails)
        // 4294967284 % 3 == 1 (seed 5 passes)
        if ((val % 3) == 0) begin
            $display("FAIL: uninitialized sync race triggered (val=%0d)", val);
            $finish;
        end else begin
            $display("PASS");
            $finish;
        end
    end
endmodule
