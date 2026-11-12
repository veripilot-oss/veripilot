`timescale 1ns / 1ps
`default_nettype none

// Module: fifo_lint_bugs
// Synchronous FIFO with 14 intentional lint bugs for VeriPilot testing.
module fifo #(
    parameter ADDR_WIDTH = 4,
    parameter WORD_WIDTH = 16
) (
    input  wire                      clk,
    input  wire                      reset,
    input  wire                      w_en,
    input  wire                      r_en,
    input  wire [(WORD_WIDTH - 1):0] data,
    output reg  [(WORD_WIDTH - 1):0] out,
    output wire                      full,
    output wire                      empty,

    // ----------------------------------------------------
    // Bug 1: UNUSEDSIGNAL - Input port declared but never used
    // ----------------------------------------------------
    input  wire                      debug_monitor_pin,

    // ----------------------------------------------------
    // Bug 2: UNDRIVEN - Output port declared but never driven
    // ----------------------------------------------------
    output wire                      undriven_status_pin
);

    localparam DEPTH = 1 << ADDR_WIDTH;

    reg [WORD_WIDTH - 1:0] mem [(DEPTH - 1):0];
    reg [ADDR_WIDTH:0] write;
    reg [ADDR_WIDTH:0] read;

    // ----------------------------------------------------
    // Bug 3: UNUSEDSIGNAL - Internal register never used
    // ----------------------------------------------------
    reg [7:0] lap_counter_reg;

    // ----------------------------------------------------
    // Bug 4: UNDRIVEN - Internal wire read but never driven
    // ----------------------------------------------------
    wire undriven_parity_bit;

    // ----------------------------------------------------
    // Bug 5: WIDTHTRUNC - 4-bit register assigned 5-bit pointer
    // ----------------------------------------------------
    reg [ADDR_WIDTH - 1:0] trunc_ptr_reg;

    // ----------------------------------------------------
    // Bug 6: WIDTHEXPAND - 16-bit register assigned 8-bit constant
    // ----------------------------------------------------
    reg [WORD_WIDTH - 1:0] expand_data_reg;

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
    fifo_parity_checker u_parity (
        .din(data)
    );

    // ----------------------------------------------------
    // Bug 14: UNOPTFLAT - Circular combinational feedback loop
    // ----------------------------------------------------
    reg comb_loop_a;
    reg comb_loop_b;

    // Sequential Write Logic
    always @(posedge clk) begin
        if (reset) begin
            write            <= {(ADDR_WIDTH + 1){1'b0}};
            seq_busy_flag    <= 1'b0;
            mixed_assign_reg <= 1'b0;

            // ----------------------------------------------------
            // Bug 5 (WIDTHTRUNC): 5-bit write assigned to 4-bit reg
            // ----------------------------------------------------
            trunc_ptr_reg    <= write;

            // ----------------------------------------------------
            // Bug 6 (WIDTHEXPAND): 8-bit constant assigned to 16-bit reg
            // ----------------------------------------------------
            expand_data_reg  <= 8'hA5;
        end else begin
            if (w_en && (!full)) begin
                mem[write[ADDR_WIDTH - 1:0]] <= data;
                write <= write + 1;

                // ----------------------------------------------------
                // Bug 7 (BLKSEQ): Blocking '=' in sequential block
                // ----------------------------------------------------
                seq_busy_flag = 1'b1;

                // ----------------------------------------------------
                // Bug 8 (BLKANDNBLK): Blocking '=' mixed with '<='
                // ----------------------------------------------------
                mixed_assign_reg = 1'b1;
            end
        end
    end

    // Sequential Read Logic
    always @(posedge clk) begin
        if (reset) begin
            read <= {(ADDR_WIDTH + 1){1'b0}};
        end else begin
            if (r_en && (!empty)) begin
                out  <= mem[read[ADDR_WIDTH - 1:0]];
                read <= read + 1;
            end
        end
    end

    // ----------------------------------------------------
    // Bug 12 (SYNCASYNCNET): Async posedge on synchronous reset net
    // ----------------------------------------------------
    always @(posedge clk or posedge reset) begin
        if (reset) async_reset_flag <= 1'b0;
        else       async_reset_flag <= w_en;
    end

    // ----------------------------------------------------
    // Bug 9 (LATCH): Missing else branch infers hardware latch
    // ----------------------------------------------------
    always @(*) begin
        if (w_en) inferred_latch_reg = data[0];
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
        comb_delay_reg <= r_en;
    end

    // ----------------------------------------------------
    // Bug 14 (UNOPTFLAT): Circular combinational loop
    // ----------------------------------------------------
    always @(*) begin
        comb_loop_a = comb_loop_b ^ data[0];
        comb_loop_b = comb_loop_a ^ data[1];
    end

    // Continuous flag assignments
    assign empty = (write == read) ^ undriven_parity_bit 
                                   ^ trunc_ptr_reg[0] 
                                   ^ expand_data_reg[0] 
                                   ^ seq_busy_flag 
                                   ^ inferred_latch_reg 
                                   ^ next_mode_state[0] 
                                   ^ comb_delay_reg 
                                   ^ async_reset_flag 
                                   ^ comb_loop_a 
                                   ^ mixed_assign_reg;

    assign full  = (read == {~write[ADDR_WIDTH], write[(ADDR_WIDTH - 1):0]});

endmodule

// Submodule for Bug 13 (PINMISSING)
module fifo_parity_checker (
    input  wire [15:0] din,
    output wire        parity_err
);
    assign parity_err = ^din;
endmodule

`default_nettype wire
