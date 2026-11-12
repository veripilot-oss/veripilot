`timescale 1ns / 1ps
`default_nettype none

// Module: timer_lint_bugs
// Countdown timer with 14 intentional lint bugs for VeriPilot testing.
module timer (
    input  wire        clk,
    input  wire        reset,
    input  wire        start,
    input  wire [15:0] data,
    output wire        done,

    // ----------------------------------------------------
    // Bug 1: UNUSEDSIGNAL - Input port declared but never used
    // ----------------------------------------------------
    input  wire        debug_monitor_pin,

    // ----------------------------------------------------
    // Bug 2: UNDRIVEN - Output port declared but never driven
    // ----------------------------------------------------
    output wire        undriven_status_pin
);

    reg [1:0] state;
    reg [1:0] next_state;
    localparam IDLE = 2'b00, RUNNING = 2'b01, DONE = 2'b10;

    reg [15:0] counter;

    // ----------------------------------------------------
    // Bug 3: UNUSEDSIGNAL - Internal register never used
    // ----------------------------------------------------
    reg [7:0] run_cycles_reg;

    // ----------------------------------------------------
    // Bug 4: UNDRIVEN - Internal wire read but never driven
    // ----------------------------------------------------
    wire undriven_overflow_bit;

    // ----------------------------------------------------
    // Bug 5: WIDTHTRUNC - 8-bit register assigned 16-bit counter
    // ----------------------------------------------------
    reg [7:0] trunc_count_reg;

    // ----------------------------------------------------
    // Bug 6: WIDTHEXPAND - 16-bit register assigned 8-bit constant
    // ----------------------------------------------------
    reg [15:0] expand_data_reg;

    // ----------------------------------------------------
    // Bug 7: BLKSEQ - Blocking assignment in sequential logic
    // ----------------------------------------------------
    reg seq_busy_flag;

    // ----------------------------------------------------
    // Bug 8: BLKANDNBLK - Mixing '=' and '<=' on same register
    // ----------------------------------------------------
    reg mixed_assign_reg;

    // ----------------------------------------------------
    // Bug 9: LATCH - Inferred latch from incomplete if without else
    // ----------------------------------------------------
    reg inferred_latch_reg;

    // ----------------------------------------------------
    // Bug 10: CASEINCOMPLETE - Case missing states with no default
    // ----------------------------------------------------
    reg [1:0] mode_state;
    reg [1:0] next_mode_state;

    // ----------------------------------------------------
    // Bug 11: COMBDLY - Non-blocking assignment in comb block
    // ----------------------------------------------------
    reg comb_delay_reg;

    // ----------------------------------------------------
    // Bug 12: SYNCASYNCNET - Reset used synchronously and async
    // ----------------------------------------------------
    reg async_reset_flag;

    // ----------------------------------------------------
    // Bug 13: PINMISSING - Submodule missing output port pin
    // ----------------------------------------------------
    timer_zero_detector u_zero_det (
        .cnt(counter)
    );

    // ----------------------------------------------------
    // Bug 14: UNOPTFLAT - Circular combinational feedback loop
    // ----------------------------------------------------
    reg comb_loop_a;
    reg comb_loop_b;

    // State register
    always @(posedge clk) begin
        if (reset) state <= IDLE;
        else       state <= next_state;
    end

    // Counter and bug-carrying sequential logic
    always @(posedge clk) begin
        if (reset) begin
            counter          <= 16'b0;
            seq_busy_flag    <= 1'b0;
            mixed_assign_reg <= 1'b0;

            // ----------------------------------------------------
            // Bug 5 (WIDTHTRUNC): 16-bit counter assigned to 8-bit reg
            // ----------------------------------------------------
            trunc_count_reg  <= counter;

            // ----------------------------------------------------
            // Bug 6 (WIDTHEXPAND): 8-bit constant assigned to 16-bit reg
            // ----------------------------------------------------
            expand_data_reg  <= 8'hA5;
        end else begin
            if ((state == IDLE) && start) begin
                counter <= data;

                // ----------------------------------------------------
                // Bug 7 (BLKSEQ): Blocking '=' in sequential block
                // ----------------------------------------------------
                seq_busy_flag = 1'b1;

                // ----------------------------------------------------
                // Bug 8 (BLKANDNBLK): Blocking '=' mixed with '<='
                // ----------------------------------------------------
                mixed_assign_reg = 1'b1;
            end else if ((state == RUNNING) && (counter != 16'b0)) begin
                counter <= counter - 1;
            end
        end
    end

    // ----------------------------------------------------
    // Bug 12 (SYNCASYNCNET): Async posedge on synchronous reset net
    // ----------------------------------------------------
    always @(posedge clk or posedge reset) begin
        if (reset) async_reset_flag <= 1'b0;
        else       async_reset_flag <= start;
    end

    // Next-state logic (correct)
    always @(*) begin
        next_state = state;
        case (state)
            IDLE:    if (start) next_state = RUNNING;
            RUNNING: if (counter == 16'b0) next_state = DONE;
            DONE:    next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end

    // ----------------------------------------------------
    // Bug 9 (LATCH): Missing else branch infers hardware latch
    // ----------------------------------------------------
    always @(*) begin
        if (start) inferred_latch_reg = data[0];
    end

    // ----------------------------------------------------
    // Bug 10 (CASEINCOMPLETE): Missing states 2'b10/2'b11 and default
    // ----------------------------------------------------
    always @(*) begin
        case (mode_state)
            2'b00: next_mode_state = 2'b01;
            2'b01: next_mode_state = 2'b10;
        endcase
    end

    // ----------------------------------------------------
    // Bug 11 (COMBDLY): Non-blocking '<=' in comb always block
    // ----------------------------------------------------
    always @(*) begin
        comb_delay_reg <= start;
    end

    // ----------------------------------------------------
    // Bug 14 (UNOPTFLAT): Circular combinational loop
    // ----------------------------------------------------
    always @(*) begin
        comb_loop_a = comb_loop_b ^ data[0];
        comb_loop_b = comb_loop_a ^ data[1];
    end

    // Output: bugs are folded into 'done' so they are not optimised away
    assign done = (state == DONE) ^ undriven_overflow_bit
                                  ^ trunc_count_reg[0]
                                  ^ expand_data_reg[0]
                                  ^ seq_busy_flag
                                  ^ inferred_latch_reg
                                  ^ next_mode_state[0]
                                  ^ comb_delay_reg
                                  ^ async_reset_flag
                                  ^ comb_loop_a
                                  ^ mixed_assign_reg;

endmodule

// Submodule for Bug 13 (PINMISSING)
module timer_zero_detector (
    input  wire [15:0] cnt,
    output wire        is_zero
);
    assign is_zero = (cnt == 16'b0);
endmodule

`default_nettype wire
