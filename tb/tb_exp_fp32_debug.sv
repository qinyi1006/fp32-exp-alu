`timescale 1ns/1ps
// Simulation-only debug testbench. The runner generates the two include files.
module tb_exp_fp32_debug;
    reg [31:0] x;
    wire [31:0] y;
    integer input_fd, snapshot_fd, event_fd, status, count;
    reg [31:0] next_x, case_id;
    reg [63:0] update_seq;
    reg capture;
    reg [4095:0] input_path, snapshot_path, event_path;
    exp_fp32 dut(.x(x), .y(y));

    task dump_snapshot;
        begin
            // Generated $fwrite for every elaborated-source wire, including LUTs.
            `include "debug_snapshot.svh"
        end
    endtask

    // One monitor per DUT signal: retain delta-cycle changes, including glitches.
    `include "debug_monitors.svh"

    initial begin
        capture = 0;
        update_seq = 0;
        case_id = 0;
        count = 0;
        if (!$value$plusargs("inputs=%s", input_path)) $fatal(1, "Missing +inputs");
        if (!$value$plusargs("snapshots=%s", snapshot_path)) $fatal(1, "Missing +snapshots");
        if (!$value$plusargs("events=%s", event_path)) $fatal(1, "Missing +events");
        input_fd = $fopen(input_path, "r");
        snapshot_fd = $fopen(snapshot_path, "w");
        event_fd = $fopen(event_path, "w");
        if (input_fd == 0 || snapshot_fd == 0 || event_fd == 0)
            $fatal(1, "Cannot open debug input/output files");
        $timeformat(-9, 0, "", 0);
        // Allow static LUT values to initialize before applying the first case.
        #1;
        status = $fscanf(input_fd, "%h\n", next_x);
        while (status == 1) begin
            case_id = count;
            capture = 1;
            x = next_x;
            #1; // Settle all zero-delay combinational activity for this input.
            capture = 0;
            dump_snapshot;
            $display("case=%08h x=%08h y=%08h", case_id, x, y);
            count = count + 1;
            status = $fscanf(input_fd, "%h\n", next_x);
        end
        if (!$feof(input_fd)) $fatal(1, "Malformed inputs after %0d cases", count);
        if (count == 0) $fatal(1, "No debug inputs");
        $fclose(input_fd);
        $fclose(snapshot_fd);
        $fclose(event_fd);
        $display("DEBUG COMPLETE: %0d cases, %0d signal updates", count, update_seq);
        $finish;
    end
endmodule
