`timescale 1ns / 1ps

module tb_spi;

parameter CLK_DIV = 4;

reg        clk, reset, start;
reg  [7:0] data_in;
wire [7:0] data_out;
wire       busy, done;
wire       sclk, mosi, cs_n;
wire       miso;

integer error;
integer i, cycles, seed;
reg [31:0] rnd;

spi #(.CLK_DIV(CLK_DIV)) dut (
    .clk(clk),
    .reset(reset),
    .start(start),
    .data_in(data_in),
    .data_out(data_out),
    .busy(busy),
    .done(done),
    .sclk(sclk),
    .mosi(mosi),
    .cs_n(cs_n),
    .miso(miso)
);

initial clk = 0;
always #5 clk = ~clk;

// watchdog
initial begin
    #20000000;
    $display("FAIL Timeout");
    $stop;
end

// ------------------------------------------------------------
// Fake slave (mode 0): puts its first bit on miso when cs_n falls,
// then shifts a new bit out on every falling edge of sclk.
// It reads mosi on every rising edge of sclk.
// ------------------------------------------------------------
reg [7:0] s_tx_byte;      // byte the slave will send back
reg [7:0] s_shift;
reg [7:0] s_rx;           // byte the slave received from the master
reg       s_miso;
integer   rise_count;

assign miso = s_miso;

always @(negedge cs_n) begin
    s_shift = s_tx_byte;
    s_miso  = s_tx_byte[7];
    rise_count = 0;
end

always @(posedge sclk) begin
    s_rx = {s_rx[6:0], mosi};
    rise_count = rise_count + 1;
end

always @(negedge sclk) begin
    if (!cs_n) begin
        s_shift = {s_shift[6:0], 1'b0};
        s_miso  = s_shift[7];
    end
end

// ------------------------------------------------------------
// One full transfer, with checks
// ------------------------------------------------------------
task do_xfer(input [7:0] tx, input [7:0] slave_byte);
    begin
        @(negedge clk);
        s_tx_byte = slave_byte;
        data_in   = tx;
        start     = 1'b1;
        @(negedge clk);
        start     = 1'b0;
        cycles    = 0;                   // start edge has passed

        if (busy !== 1'b1) begin
            $display("FAIL: busy not high after start at %0t", $time);
            error = error + 1;
        end
        if (cs_n !== 1'b0) begin
            $display("FAIL: cs_n not low during transfer at %0t", $time);
            error = error + 1;
        end

        while (done !== 1'b1 && cycles < 100000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end

        if (cycles != 16 * CLK_DIV) begin
            $display("FAIL: done after %0d cycles, expected %0d at %0t",
                     cycles, 16 * CLK_DIV, $time);
            error = error + 1;
        end
        if (data_out !== slave_byte) begin
            $display("FAIL: data_out = %h but slave sent %h at %0t",
                     data_out, slave_byte, $time);
            error = error + 1;
        end
        if (s_rx !== tx) begin
            $display("FAIL: slave received %h but master sent %h at %0t",
                     s_rx, tx, $time);
            error = error + 1;
        end
        if (rise_count != 8) begin
            $display("FAIL: %0d sclk rising edges, expected 8 at %0t",
                     rise_count, $time);
            error = error + 1;
        end
        if (cs_n !== 1'b1) begin
            $display("FAIL: cs_n not high when done at %0t", $time);
            error = error + 1;
        end

        // back to idle, done lasts one cycle
        @(negedge clk);
        if (done !== 1'b0 || busy !== 1'b0 || sclk !== 1'b0) begin
            $display("FAIL: not idle after done (done=%b busy=%b sclk=%b) at %0t",
                     done, busy, sclk, $time);
            error = error + 1;
        end
    end
endtask

initial begin
    reset     = 1'b1;
    start     = 1'b0;
    data_in   = 8'h00;
    s_tx_byte = 8'h00;
    s_miso    = 1'b0;
    s_rx      = 8'h00;
    rise_count = 0;
    error     = 0;

    repeat (4) @(posedge clk);
    @(negedge clk);
    reset = 1'b0;
    #1;
    if (cs_n !== 1'b1 || sclk !== 1'b0 || busy !== 1'b0 || done !== 1'b0) begin
        $display("FAIL: bad idle state after reset at %0t", $time);
        error = error + 1;
    end

    // 1. Directed transfers
    do_xfer(8'hA5, 8'h3C);
    do_xfer(8'h00, 8'hFF);
    do_xfer(8'hFF, 8'h00);
    do_xfer(8'h01, 8'h80);      // single-bit values catch bit-order bugs
    do_xfer(8'h80, 8'h01);
    do_xfer(8'h55, 8'hAA);

    // 2. start while busy must be ignored
    @(negedge clk);
    s_tx_byte = 8'hC3;
    data_in   = 8'h5A;
    start     = 1'b1;
    @(negedge clk);
    start     = 1'b0;
    repeat (10) @(negedge clk);
    data_in = 8'hFF;            // would corrupt the byte if it were re-captured
    start   = 1'b1;
    @(negedge clk);
    start   = 1'b0;
    while (done !== 1'b1) @(negedge clk);
    if (s_rx !== 8'h5A || data_out !== 8'hC3) begin
        $display("FAIL: start during busy changed the transfer (rx=%h out=%h) at %0t",
                 s_rx, data_out, $time);
        error = error + 1;
    end
    @(negedge clk);

    // 3. reset in the middle of a transfer
    @(negedge clk);
    s_tx_byte = 8'hF0;
    data_in   = 8'h0F;
    start     = 1'b1;
    @(negedge clk);
    start     = 1'b0;
    repeat (20) @(negedge clk);
    reset = 1'b1;
    @(negedge clk);
    reset = 1'b0;
    #1;
    if (cs_n !== 1'b1 || sclk !== 1'b0 || busy !== 1'b0) begin
        $display("FAIL: not idle after mid-transfer reset at %0t", $time);
        error = error + 1;
    end
    repeat (3) @(negedge clk);
    do_xfer(8'h96, 8'h69);      // still works after reset

    // 4. Random transfers, fixed seed
    seed = 1;
    for (i = 0; i < 100; i = i + 1) begin
        rnd = $random(seed);
        do_xfer(rnd[7:0], rnd[15:8]);
    end

    if (error == 0) $display("PASS");
    else begin
        $display("FAIL: %0d errors", error);
        $stop;
    end
    $finish;
end

endmodule
