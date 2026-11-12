`default_nettype none

// SPI master, mode 0 (CPOL=0, CPHA=0), 8 bits per transfer, MSB first.
//
// Ports:
//   start    : pulse for 1 cycle (while idle) to begin a transfer
//   data_in  : byte to send, captured when start is accepted
//   data_out : byte received, valid when done pulses
//   busy     : high during a transfer
//   done     : 1-cycle pulse when the transfer finishes
//   sclk, mosi, cs_n : SPI outputs (cs_n is active low)
//   miso     : SPI input from the slave
module spi #(
    parameter CLK_DIV = 4          // half-period of sclk, in clk cycles
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
    input  wire       miso
);

localparam IDLE=2'b00, TRANSFER=2'b01, DONE = 2'b10;
localparam [15:0] LAST = CLK_DIV-1;

reg [1:0] state;
reg [15:0] div_cnt;
reg sclk_r;
reg [2:0] bit_cnt;
reg [7:0] shift_out;
reg [7:0] shift_in;

always @(posedge clk) begin
    if(reset) begin
        state <= IDLE;
        div_cnt <= 16'd0;
        sclk_r <= 1'b0;
        bit_cnt <= 3'd0;
        shift_out <= 8'd0;
        shift_in <= 8'd0;
    end
    else begin
        case(state)
            IDLE:begin
                sclk_r <= 1'b0;
                div_cnt <= 16'd0;
                bit_cnt <= 3'd0;
                if (start) begin
                    shift_out <= data_in;
                    state <= TRANSFER;
                end
            end

            TRANSFER: begin
                if(div_cnt == LAST) begin
                    div_cnt <= 16'd0;
                    sclk_r <= ~sclk_r;

                    if(!sclk_r) begin
                        shift_in <= {shift_in[6:0],miso};
                    end else begin
                        shift_out <= {shift_out[6:0],1'b0};
                        bit_cnt <= bit_cnt + 3'd1;
                        if(bit_cnt == 3'd7) 
                            state <= DONE;
                    end
                end else begin
                    div_cnt <= div_cnt + 16'd1;
                end
            end

            DONE:
                state <= IDLE;

            default:
                state <= IDLE;
        endcase
    end
end

assign sclk = sclk_r;
assign mosi = shift_out[7];
assign cs_n = (state != TRANSFER);
assign busy = (state != IDLE);
assign done = (state == DONE);
assign data_out = shift_in;

endmodule

`default_nettype wire
