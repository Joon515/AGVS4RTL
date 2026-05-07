module seq_done_real_llm_trace (
    input wire i_clk,
    input wire i_rst_n,
    output wire o_done
);

    reg done_reg;

    always @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            done_reg <= 1'b0;
        end else begin
            done_reg <= 1'b1;
        end
    end

    assign o_done = done_reg;

endmodule
