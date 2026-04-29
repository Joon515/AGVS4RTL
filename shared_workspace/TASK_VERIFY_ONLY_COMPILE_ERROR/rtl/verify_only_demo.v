module verify_only_demo(
    input wire i_clk,
    input wire i_rst_n,
    input wire [7:0] i_data,
    output reg o_done
);

always @(posedge i_clk or negedge i_rst_n) begin
    if (!i_rst_n) begin
        o_done <= 1'b0;
    end else begin
        o_done <= |i_data
    end
end

endmodule
