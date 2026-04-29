module seq_done_real_llm_trace2 (
    input  wire i_clk,
    input  wire i_rst_n,
    output wire o_done
);
    reg o_done_reg;

    always @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            o_done_reg <= 1'b0;
        end else begin
            o_done_reg <= 1'b1;
        end
    end

    assign o_done = o_done_reg;
endmodule
