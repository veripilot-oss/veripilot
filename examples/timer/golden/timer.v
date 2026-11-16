`default_nettype none
module timer (input clk,
              input reset,
              input start, 
              input [15:0]data,         
              output done
);

    reg [1:0] state;
    reg [1:0] next_state;
    localparam  IDLE = 2'b00, RUNNING = 2'b01, DONE = 2'b10;

    reg [15:0]counter;

    always @(posedge clk) begin
        if(reset) begin 
                    state <= IDLE;
                  end
        else 
            state <= next_state;
    end

    always @(posedge clk) begin
        if (reset) counter <= 16'b0;
        else if((state == IDLE) && start) counter <= data;
        else if ((state == RUNNING) && (counter != 16'b0)) counter <= counter - 1;
    end

    always @(*) begin
        next_state = state;     // for not infering a latch
        case (state)
            IDLE: begin
                    if(start) next_state = RUNNING;
                end

            RUNNING:begin
                        if(counter == 16'b0) next_state = DONE;
                    end

            DONE: begin
                    next_state = IDLE;
                end

            default: next_state = IDLE;
        endcase
    end

    assign done = (state == DONE);
endmodule
`default_nettype wire

