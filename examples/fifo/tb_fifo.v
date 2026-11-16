`timescale 1ns / 1ps

module tb_fifo;
reg clk, reset;
reg w_en, r_en;
reg [15:0]data;
wire [15:0] out;
wire full, empty;

reg [15:0] model [255:0];
integer m_wr, m_rd, m_count;
integer error;
reg [15:0] expected;

integer i;
integer j, seed;
reg [17:0] rnd;

    fifo dut(
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

//watchdog counter
initial begin 
    #500000;
    $display("FAIL Timeout");
    $stop;
end

// flag errors
task check_flags;
    begin 
        if (empty !== (m_count == 0) ) begin
            $display("FAIL: empty = %b but model count = %0d at %0t", empty, m_count, $time);
            error = error + 1;
        end
        if (full !== (m_count == 16) ) begin
            $display("FAIL: full = %b but model count = %0d at %0t", full, m_count, $time);
            error = error + 1;
        end
    end
endtask

// Checking Write part
task write_word(input [15:0] d);
    begin 
        @(negedge clk);
            w_en = 1'b1;
            data = d;

        if(!full) begin
            model[m_wr % 256] = data;
            m_wr = m_wr + 1;
            m_count = m_count + 1;
        end

        @(posedge clk);
            #1;
            w_en = 1'b0;
            check_flags;
    end
endtask

//checking read part
task read_word;
    begin 
        @(negedge clk);
            r_en = 1'b1;

        if(!empty) begin
            expected = model[m_rd % 256];
            m_rd = m_rd + 1;
            m_count = m_count - 1;
        end

        @(posedge clk);
            #1;
            r_en = 1'b0;
            if (out !== expected ) begin
                $display("FAIL: out = %0d but expected = %0d at %0t", out, expected, $time);
                error = error + 1;
            end
            check_flags;
    end
endtask

task random_check;
    begin
        for (i = 0; i < 16; i = i + 1)begin
            write_word(i + 100);
        end

        for (i = 0; i < 3; i = i + 1) begin
            write_word(i + 200);
        end

        for (i = 0; i < 16; i = i + 1) begin
            read_word;     
        end
    end
endtask

reg w_ok, r_ok;

// for read and write at same cycle 
task rw_cycle (input w, input r, input[15:0] d);
    begin
        @(negedge clk);
        w_en = w;
        r_en = r;
        data = d;

        w_ok = (w_en && (!full));
        r_ok = (r_en && (!empty));

        if(w_ok) begin
            model[m_wr % 256] = data;
            m_wr = m_wr + 1;
            m_count = m_count + 1;
        end

        if(r_ok) begin
            expected = model[m_rd % 256];
            m_rd = m_rd + 1;
            m_count = m_count - 1;
        end

        @(posedge clk);
        #1;
        w_en = 1'b0;
        r_en = 1'b0;
        if (r_ok && (out !== expected)) begin
                $display("FAIL: out = %0d but expected = %0d at %0t", out, expected, $time);
                error = error + 1;
            end
        check_flags;
    end
endtask

// Holding reset thing for first few clk cycles
initial begin 
    reset = 1'b1;
    w_en = 1'b0;
    r_en = 1'b0;
    data = 16'b0;

    m_wr = 0; m_rd = 0; 
    m_count = 0;
    error = 0;
    expected = 16'b0;  

    repeat (4) @(posedge clk);

    @(negedge clk);
    reset = 1'b0;
    #1;
    check_flags;

    random_check;
    
    // To check if read ponter has advanced during empty reads
    for (i = 0; i < 3; i = i + 1) rw_cycle(0, 1, 16'd0);
    rw_cycle(1, 0, 16'd555);
    rw_cycle(0, 1, 16'd0);

    //6a: Get it half full 
    for (i = 0; i < 8; i = i + 1) rw_cycle(1, 0, 300 + i);
    //6b: read and write in the same cycle
    for (i = 0; i < 40; i = i + 1) rw_cycle(1, 1, 400 + i);
    //6c: drain
    for (i = 0; i < 8; i = i + 1) rw_cycle(0, 1, 16'd0);
    //6d: both enables, FIFO empty
    rw_cycle(1, 1, 16'd700);
    rw_cycle(0, 1, 16'd0);
    //6e: both enables, FIFO full
    for (i = 0; i < 16; i = i + 1) rw_cycle(1, 0, 800 + i);
    rw_cycle(1, 1, 16'd900);
    for (i = 0; i < 16; i = i + 1) rw_cycle(0, 1, 16'd0);
    
    //To circle for several laps 
    for (j = 0; j < 5; j = j + 1) random_check;

    // random tests with fixed seed
    seed = 1;
    for (i = 0; i < 5000; i = i + 1) begin
        rnd = $random(seed);
        rw_cycle(rnd[0], rnd[1], rnd[17:2]);
    end
    for (i = 0; i < 20; i = i + 1) rw_cycle(0, 1, 16'd0);

    // Total Errors
    if (error == 0) $display("PASS"); 
    else begin 
        $display("FAIL: %0d errors", error);
        $stop;
    end
    $finish;
end

endmodule

