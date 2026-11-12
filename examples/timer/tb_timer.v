`timescale 1ns / 1ps

module tb_timer;
reg         clk, reset, start;
reg  [15:0] data;
wire        done;

integer error;
integer i, seed, cycles;
reg [31:0] rnd;

// Reference model (state: 0 = IDLE, 1 = RUNNING, 2 = DONE)
integer    m_state;
reg [15:0] m_counter;

timer dut (
    .clk(clk),
    .reset(reset),
    .start(start),
    .data(data),
    .done(done)
);

initial clk = 0;
always #5 clk = ~clk;

// watchdog
initial begin
    #5000000;
    $display("FAIL Timeout");
    $stop;
end

// Reference model: updates on every rising edge using the inputs
// that were driven at the previous negedge.
always @(posedge clk) begin
    if (reset) begin
        m_state   <= 0;
        m_counter <= 16'b0;
    end else begin
        case (m_state)
            0: if (start) begin
                   m_counter <= data;
                   m_state   <= 1;
               end
            1: begin
                   if (m_counter != 16'b0) m_counter <= m_counter - 1;
                   else                    m_state   <= 2;
               end
            2: m_state <= 0;
            default: m_state <= 0;
        endcase
    end
end

// Compare DUT against model once per cycle, just after the edge
task check_done;
    begin
        if (done !== (m_state == 2)) begin
            $display("FAIL: done = %b but model state = %0d at %0t", done, m_state, $time);
            error = error + 1;
        end
    end
endtask

always @(posedge clk) begin
    #1;
    if (!$isunknown(m_state)) check_done;
end

// One-cycle start pulse, then wait for done and check the latency.
// Expected: done goes high (n + 1) clock edges after the start edge.
task run_timer(input [15:0] n);
    begin
        @(negedge clk);
        start = 1'b1;
        data  = n;
        @(negedge clk);
        start = 1'b0;
        cycles = 0;                       // the start edge has passed

        while (done !== 1'b1 && cycles < 70000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end

        if (cycles != n + 1) begin
            $display("FAIL: n = %0d, done after %0d cycles, expected %0d at %0t",
                     n, cycles, n + 1, $time);
            error = error + 1;
        end

        // done must last exactly one cycle
        @(negedge clk);
        if (done !== 1'b0) begin
            $display("FAIL: done stayed high for more than one cycle at %0t", $time);
            error = error + 1;
        end
    end
endtask

// Drive random-style input for one cycle
task drive(input s, input [15:0] d);
    begin
        @(negedge clk);
        start = s;
        data  = d;
    end
endtask

initial begin
    reset = 1'b1;
    start = 1'b0;
    data  = 16'b0;
    error = 0;

    repeat (4) @(posedge clk);
    @(negedge clk);
    reset = 1'b0;
    #1;
    if (done !== 1'b0) begin
        $display("FAIL: done not low after reset at %0t", $time);
        error = error + 1;
    end

    // 1. Directed latency checks
    run_timer(16'd0);
    run_timer(16'd1);
    run_timer(16'd2);
    run_timer(16'd5);
    run_timer(16'd16);
    run_timer(16'd255);
    run_timer(16'd1000);

    // 2. start must be ignored while RUNNING (counter must not reload)
    drive(1, 16'd10);
    drive(0, 16'd0);
    repeat (3) drive(1, 16'd50);          // extra starts mid-count
    drive(0, 16'd0);
    cycles = 0;
    repeat (20) begin
        @(negedge clk);
        cycles = cycles + 1;
    end

    // 3. start while DONE must not restart immediately
    drive(1, 16'd2);
    drive(0, 16'd0);
    repeat (2) @(negedge clk);
    drive(1, 16'd7);                      // likely lands in DONE or just after
    drive(0, 16'd0);
    repeat (20) @(negedge clk);

    // 4. reset in the middle of a count
    drive(1, 16'd100);
    drive(0, 16'd0);
    repeat (10) @(negedge clk);
    reset = 1'b1;
    @(negedge clk);
    reset = 1'b0;
    #1;
    if (done !== 1'b0) begin
        $display("FAIL: done high right after mid-count reset at %0t", $time);
        error = error + 1;
    end
    repeat (5) @(negedge clk);
    run_timer(16'd3);                     // timer still works after reset

    // 5. reset while DONE is high
    drive(1, 16'd1);
    drive(0, 16'd0);
    while (done !== 1'b1) @(negedge clk);
    reset = 1'b1;
    @(negedge clk);
    reset = 1'b0;
    #1;
    if (done !== 1'b0) begin
        $display("FAIL: done high after reset during DONE at %0t", $time);
        error = error + 1;
    end

    // 6. Random test with fixed seed, small counts so many runs complete
    seed = 1;
    for (i = 0; i < 20000; i = i + 1) begin
        rnd = $random(seed);
        @(negedge clk);
        start = (rnd[3:0] < 4);           // start about 25% of cycles
        data  = rnd[19:16];               // values 0..15
        reset = (rnd[31:24] == 8'd0);     // rare reset
    end
    @(negedge clk);
    reset = 1'b0;
    start = 1'b0;
    repeat (40) @(negedge clk);

    if (error == 0) $display("PASS");
    else begin
        $display("FAIL: %0d errors", error);
        $stop;
    end
    $finish;
end

endmodule
