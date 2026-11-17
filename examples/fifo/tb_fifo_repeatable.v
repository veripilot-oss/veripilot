`timescale 1ns / 1ps

// Demo testbench for triage: it fails on EVERY seed, so triage labels it "repeatable".
//
// The failure is deliberate and comes from a wrong expectation, not from a bug in the FIFO:
// after one word is written the FIFO is no longer empty, but this testbench expects it to
// still be empty. Nothing here depends on the seed, so the result never changes.
// Compare with tb_fifo_flaky.v, which fails on some seeds only.
module tb_fifo_repeatable;
    reg clk;
    reg reset;
    reg w_en;
    reg r_en;
    reg [15:0] data;
    wire [15:0] out;
    wire full;
    wire empty;

    fifo dut (
        .clk(clk),
        .reset(reset),
        .w_en(w_en),
        .r_en(r_en),
        .out(out),
        .data(data),
        .full(full),
        .empty(empty)
    );

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        reset = 1;
        w_en = 0;
        r_en = 0;
        data = 16'h0000;
        repeat (3) @(posedge clk);
        #1 reset = 0;

        // write exactly one word
        @(negedge clk);
        w_en = 1;
        data = 16'hA5A5;
        @(posedge clk);
        #1 w_en = 0;
        @(posedge clk);
        #1;

        // wrong on purpose: one word is stored, so empty is 0, not 1
        if (empty === 1'b1) begin
            $display("PASS");
        end else begin
            $display("FAIL: expected empty=1 after one write, got empty=%b (deliberately wrong expectation)", empty);
        end
        $finish;
    end
endmodule
