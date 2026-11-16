`default_nettype none
module fifo  #(
    parameter ADDR_WIDTH = 4,
    parameter WORD_WIDTH = 16
    )
           ( input clk,
             input reset,
             input w_en,
             input r_en,
             input [(WORD_WIDTH - 1):0]data,
             output reg [(WORD_WIDTH - 1):0]out,
             output full,
             output empty
);

localparam DEPTH = 1 << ADDR_WIDTH;

reg [WORD_WIDTH - 1:0] mem [(DEPTH - 1):0];
reg [ADDR_WIDTH:0] write;  //one extra bit for knowing if the memory full or empty
reg [ADDR_WIDTH:0] read;

always @(posedge clk) begin
    if(reset) write <= {(ADDR_WIDTH + 1){1'b0}}; // 5'b0 in this case
    else begin
            if(w_en && (!full)) begin
                mem[write[ADDR_WIDTH - 1:0]] <= data; 
                write <= write + 1;
            end
         end
end

always @(posedge clk) begin
    if(reset) read <= {(ADDR_WIDTH + 1){1'b0}};
    else begin
            if(r_en && (!empty)) begin
                out <= mem[read[ADDR_WIDTH - 1:0]]; 
                read <= read + 1;
            end
         end
end

assign empty = (write == read);
assign full = (read == {~write[ADDR_WIDTH],write[(ADDR_WIDTH - 1):0]});
endmodule

`default_nettype wire

