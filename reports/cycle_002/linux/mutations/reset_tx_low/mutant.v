`timescale 1ns/1ps
`default_nettype none

module uart_tx_apb #(
    parameter integer CLK_FREQ_HZ = 50_000_000,
    parameter integer BAUD_RATE   = 115_200
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] paddr,
    input  wire        psel,
    input  wire        penable,
    input  wire        pwrite,
    input  wire [31:0] pwdata,
    input  wire [3:0]  pstrb,
    input  wire [2:0]  pprot,
    output reg  [31:0] prdata,
    output reg         pready,
    output reg         pslverr,
    output reg         tx
);

    // A safe denominator lets invalid configurations reach the diagnostic.
    localparam integer SAFE_BAUD = (BAUD_RATE > 0) ? BAUD_RATE : 1;
    // Widen before addition so high clock frequencies cannot overflow.
    localparam [63:0] DIV_ROUNDED =
        (64'd1 * CLK_FREQ_HZ + SAFE_BAUD / 2) / SAFE_BAUD;
    localparam integer CLKS_PER_BIT =
        (DIV_ROUNDED < 1) ? 1 : DIV_ROUNDED;
    localparam integer COUNT_WIDTH =
        (CLKS_PER_BIT <= 1) ? 1 : $clog2(CLKS_PER_BIT);
    localparam [COUNT_WIDTH-1:0] LAST_COUNT = CLKS_PER_BIT - 1;

    localparam [31:0] DATA_REG   = 32'h0000_0000;
    localparam [31:0] STATUS_REG = 32'h0000_0004;
    localparam [1:0] IDLE  = 2'd0;
    localparam [1:0] START = 2'd1;
    localparam [1:0] DATA  = 2'd2;
    localparam [1:0] STOP  = 2'd3;

    reg [1:0] state;
    reg [7:0] shift_reg;
    reg [2:0] bit_index;
    reg [COUNT_WIDTH-1:0] baud_count;

    wire busy = (state != IDLE);
    wire baud_tick = (baud_count == LAST_COUNT);
    wire data_write = rst_n && psel && penable && pready &&
                      !pslverr && pwrite && (paddr == DATA_REG) && pstrb[0];

    // PPROT is accepted for every encoding; access policy belongs upstream.
    // Decode the entire byte address to avoid register aliases.
    always @* begin
        prdata  = 32'b0;
        pready  = 1'b0;
        pslverr = 1'b0;
        if (rst_n && psel && penable) begin
            pready = 1'b1;
            case (paddr)
                DATA_REG: begin
                    if (!pwrite)
                        pslverr = 1'b1;
                    else if (pstrb[0] && busy)
                        pready = 1'b0;
                end
                STATUS_REG: begin
                    if (pwrite)
                        pslverr = 1'b1;
                    else
                        prdata = {31'b0, busy};
                end
                default: pslverr = 1'b1;
            endcase
        end
    end

    // Rephase at each acceptance so START is always a complete bit period.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            baud_count <= {COUNT_WIDTH{1'b0}};
        else if ((state == IDLE) || baud_tick)
            baud_count <= {COUNT_WIDTH{1'b0}};
        else
            baud_count <= baud_count + 1'b1;
    end

    // Register tx to keep state/decode propagation off the serial output.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            shift_reg <= 8'b0;
            bit_index <= 3'b0;
            tx        <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    tx        <= 1'b1;
                    bit_index <= 3'b0;
                    if (data_write) begin
                        shift_reg <= pwdata[7:0];
                        state     <= START;
                        tx        <= 1'b0;
                    end
                end
                START: begin
                    if (baud_tick) begin
                        state <= DATA;
                        tx    <= shift_reg[0];
                    end
                end
                DATA: begin
                    if (baud_tick) begin
                        if (bit_index == 3'd7) begin
                            state <= STOP;
                            tx    <= 1'b1;
                        end else begin
                            bit_index <= bit_index + 1'b1;
                            shift_reg <= {1'b0, shift_reg[7:1]};
                            tx        <= shift_reg[1];
                        end
                    end
                end
                STOP: begin
                    if (baud_tick)
                        state <= IDLE;
                end
                default: begin
                    state     <= IDLE;
                    shift_reg <= 8'b0;
                    bit_index <= 3'b0;
                    tx        <= 1'b1;
                end
            endcase
        end
    end

`ifndef SYNTHESIS
    initial begin
        if ((CLK_FREQ_HZ <= 0) || (BAUD_RATE <= 0) ||
            (BAUD_RATE > CLK_FREQ_HZ))
            $fatal(1, "Require CLK_FREQ_HZ > 0 and 0 < BAUD_RATE <= CLK_FREQ_HZ");
    end
`ifdef UART_TX_DUMP_VCD
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0);
    end
`endif
`endif

endmodule

`default_nettype wire
