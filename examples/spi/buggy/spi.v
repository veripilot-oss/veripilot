`timescale 1ns / 1ps
`default_nettype none

// Module: spi_master_lint_bugs
// SPI master (mode 0) with 14 intentional lint bugs for VeriPilot testing.
module spi #(
    parameter CLK_DIV = 4
) (
    input  wire       clk,
    input  wire       reset,
    input  wire       start,
    input  wire [7:0] data_in,
    output wire [7:0] data_out,
    output wire       busy,
    output wire       done,

    output wire       sclk,
    output wire       mosi,
    output wire       cs_n,
    input  wire       miso,

    // ----------------------------------------------------
    // Bug 1: UNUSEDSIGNAL - Input port declared but never used
    // ----------------------------------------------------
    input  wire       debug_monitor_pin,

    // ----------------------------------------------------
    // Bug 2: UNDRIVEN - Output port declared but never driven
    // ----------------------------------------------------
    output wire       undriven_status_pin
);

    localparam IDLE = 2'b00, TRANSFER = 2'b01, DONE = 2'b10;
    localparam [15:0] LAST = CLK_DIV - 1;

    reg [1:0]  state;
    reg [15:0] div_cnt;
    reg        sclk_r;
    reg [2:0]  bit_cnt;
    reg [7:0]  shift_out;
    reg [7:0]  shift_in;

    // ----------------------------------------------------
    // Bug 3: UNUSEDSIGNAL - Internal register never used
    // ----------------------------------------------------
    reg [7:0] frame_counter_reg;

    // ----------------------------------------------------
    // Bug 4: UNDRIVEN - Internal wire read but never driven
    // ----------------------------------------------------
    wire undriven_parity_bit;

    // ----------------------------------------------------
    // Bug 5: WIDTHTRUNC - 4-bit register assigned 16-bit counter
    // ----------------------------------------------------
    reg [3:0] trunc_cnt_reg;

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
    spi_parity_checker u_parity (
        .din(data_in)
    );

    // ----------------------------------------------------
    // Bug 14: UNOPTFLAT - Circular combinational feedback loop
    // ----------------------------------------------------
    reg comb_loop_a;
    reg comb_loop_b;

    // Main SPI logic
    always @(posedge clk) begin
        if (reset) begin
            state            <= IDLE;
            div_cnt          <= 16'd0;
            sclk_r           <= 1'b0;
            bit_cnt          <= 3'd0;
            shift_out        <= 8'd0;
            shift_in         <= 8'd0;
            seq_busy_flag    <= 1'b0;
            mixed_assign_reg <= 1'b0;

            // ----------------------------------------------------
            // Bug 5 (WIDTHTRUNC): 16-bit counter assigned to 4-bit reg
            // ----------------------------------------------------
            trunc_cnt_reg    <= div_cnt;

            // ----------------------------------------------------
            // Bug 6 (WIDTHEXPAND): 8-bit constant assigned to 16-bit reg
            // ----------------------------------------------------
            expand_data_reg  <= 8'hA5;
        end else begin
            case (state)
                IDLE: begin
                    sclk_r  <= 1'b0;
                    div_cnt <= 16'd0;
                    bit_cnt <= 3'd0;
                    if (start) begin
                        shift_out <= data_in;
                        state     <= TRANSFER;

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

                TRANSFER: begin
                    if (div_cnt == LAST) begin
                        div_cnt <= 16'd0;
                        sclk_r  <= ~sclk_r;

                        if (!sclk_r) begin
                            shift_in <= {shift_in[6:0], miso};
                        end else begin
                            shift_out <= {shift_out[6:0], 1'b0};
                            bit_cnt   <= bit_cnt + 3'd1;
                            if (bit_cnt == 3'd7) state <= DONE;
                        end
                    end else begin
                        div_cnt <= div_cnt + 16'd1;
                    end
                end

                DONE: state <= IDLE;

                default: state <= IDLE;
            endcase
        end
    end

    // ----------------------------------------------------
    // Bug 12 (SYNCASYNCNET): Async posedge on synchronous reset net
    // ----------------------------------------------------
    always @(posedge clk or posedge reset) begin
        if (reset) async_reset_flag <= 1'b0;
        else       async_reset_flag <= start;
    end

    // ----------------------------------------------------
    // Bug 9 (LATCH): Missing else branch infers hardware latch
    // ----------------------------------------------------
    always @(*) begin
        if (start) inferred_latch_reg = data_in[0];
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
        comb_delay_reg <= miso;
    end

    // ----------------------------------------------------
    // Bug 14 (UNOPTFLAT): Circular combinational loop
    // ----------------------------------------------------
    always @(*) begin
        comb_loop_a = comb_loop_b ^ data_in[0];
        comb_loop_b = comb_loop_a ^ data_in[1];
    end

    // Outputs: bugs are folded into 'busy' so they are not optimised away
    assign sclk     = sclk_r;
    assign mosi     = shift_out[7];
    assign cs_n     = (state != TRANSFER);
    assign done     = (state == DONE);
    assign data_out = shift_in;
    assign busy     = (state != IDLE) ^ undriven_parity_bit
                                      ^ trunc_cnt_reg[0]
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
module spi_parity_checker (
    input  wire [7:0] din,
    output wire       parity_err
);
    assign parity_err = ^din;
endmodule

`default_nettype wire
