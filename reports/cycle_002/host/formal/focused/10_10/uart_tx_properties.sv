`default_nettype none

// One SAT step denotes one rising PCLK edge. Inputs are nondeterministic.
// async2sync makes this a sampled-reset model, not an analog/reset sign-off.
module uart_tx_properties #(
    parameter integer FORMAL_CLOCK = 30,
    parameter integer FORMAL_BAUD = 10
) (
    input wire clk,
    output wire witness_goal
);
    localparam integer D = (FORMAL_CLOCK + FORMAL_BAUD / 2) / FORMAL_BAUD;
    localparam integer FRAME_CYCLES = 10 * D;
    localparam integer AGE_W = $clog2(FRAME_CYCLES + 1);
    (* anyseq *) reg rst_n;
    (* anyseq *) reg [31:0] paddr;
    (* anyseq *) reg psel, penable, pwrite;
    (* anyseq *) reg [31:0] pwdata;
    (* anyseq *) reg [3:0] pstrb;
    (* anyseq *) reg [2:0] pprot;
    wire [31:0] prdata;
    wire pready, pslverr, tx;

    uart_tx_apb #(.CLK_FREQ_HZ(FORMAL_CLOCK), .BAUD_RATE(FORMAL_BAUD)) dut (
        .clk(clk), .rst_n(rst_n), .paddr(paddr), .psel(psel),
        .penable(penable), .pwrite(pwrite), .pwdata(pwdata),
        .pstrb(pstrb), .pprot(pprot), .prdata(prdata),
        .pready(pready), .pslverr(pslverr), .tx(tx)
    );

    // Independent frame-age reference: no DUT internal signal is accessed.
    reg past_valid = 0;
    reg ref_active = 0;
    reg [AGE_W-1:0] ref_age = 0;
    reg [9:0] ref_frame = 10'h3ff;
    reg seen_complete = 0, seen_stall = 0, seen_error = 0;
    wire access = rst_n && psel && penable;
    wire data_direction = paddr == 0 && pwrite;
    wire status_direction = paddr == 4 && !pwrite;
    wire exp_ready = access && !(data_direction && pstrb[0] && ref_active);
    wire exp_error = access && !(data_direction || status_direction);
    wire [31:0] exp_data = access && status_direction ? {31'b0, ref_active} : 0;
    wire exp_tx = !rst_n || !ref_active ? 1'b1 : ref_frame[ref_age / D];
    wire accept_byte = exp_ready && !exp_error && data_direction && pstrb[0];
    assign witness_goal = seen_complete && seen_stall && seen_error;

    initial assume(!rst_n);

    // APB requester assumptions: SETUP then ACCESS, stable through waits,
    // no PENABLE without PSEL, zero read strobes, reset aborts the transfer.
    always @(posedge clk) begin
        past_valid <= 1;
        if (!rst_n) begin
            assume(!psel && !penable);
        end else begin
            assume(!penable || psel);
            if (!pwrite) assume(pstrb == 0);
            if (!past_valid || !$past(rst_n)) begin
                assume(!penable);
            end else if ($past(psel && (!penable || !exp_ready))) begin
                assume(psel && penable);
                assume($stable(paddr));
                assume($stable(pwrite));
                assume($stable(pwdata));
                assume($stable(pstrb));
                assume($stable(pprot));
            end else begin
                assume(!penable);
            end
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            ref_active <= 0;
            ref_age <= 0;
            ref_frame <= 10'h3ff;
        end else begin
            if (ref_active) begin
                if (ref_age == FRAME_CYCLES - 1) begin
                    ref_active <= 0;
                    ref_age <= 0;
                    seen_complete <= 1;
                end else ref_age <= ref_age + 1'b1;
            end
            if (accept_byte) begin
                ref_active <= 1;
                ref_age <= 0;
                ref_frame <= {1'b1, pwdata[7:0], 1'b0};
            end
            if (access && !exp_ready) seen_stall <= 1;
            if (exp_error) seen_error <= 1;
        end
    end

    always @* begin
        if (past_valid) begin
            assert(pready == exp_ready);
            assert(pslverr == exp_error);
            assert(prdata == exp_data);
            assert(tx == exp_tx);
            assert(!pslverr || (psel && penable && pready));
        end
    end
endmodule

`default_nettype wire
