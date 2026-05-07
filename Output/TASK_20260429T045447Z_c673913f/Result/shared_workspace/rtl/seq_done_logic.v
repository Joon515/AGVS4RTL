module seq_done_logic (
    input wire i_clk,
    input wire i_rst_n,
    output reg o_done
);
    always @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            o_done <= 1'b0;
        end else begin
            o_done <= 1'b1;
        end
    end
endmodule
