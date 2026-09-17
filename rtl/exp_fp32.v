`timescale 1ns/1ps
`default_nettype none
// Finite FP32 x in [-64,64] only. Purely feed-forward combinational datapath.
// Q24 means 24 fractional bits, not a 24-bit total width.
module exp_fp32(input wire [31:0] x, output wire [31:0] y);
    // Stage 1: decode and truncate magnitude toward zero into Q24.
    wire [7:0] input_exp = x[30:23];
    wire [23:0] input_sig = {(|input_exp), x[22:0]};
    wire [7:0] left_amount = input_exp - 8'd126;
    wire [7:0] right_amount = 8'd126 - input_exp;
    wire [30:0] magnitude = (input_exp >= 8'd126)
        ? ({7'b0, input_sig} << left_amount)
        : ({7'b0, input_sig} >> right_amount);
    wire negative = x[31];
    // please add tie pipe here
    // Boundary 1: register magnitude and negative.

    // Stage 2: multiply magnitudes, then form the floor in two's complement.
    wire [61:0] log_product = magnitude * 31'd1549082005;
    wire [31:0] log_integer = log_product[61:30];
    wire log_fraction_zero = ~(|log_product[29:0]);
    // floor(-P / 2^30) = ~floor(P / 2^30) + (remainder == 0).
    // Applying the remainder correction is essential for negative inputs.
    wire [31:0] negative_y_q24 = (~log_integer) + {31'b0, log_fraction_zero};
    wire [31:0] y_q24 = negative ? negative_y_q24 : log_integer;
    wire [7:0] k = y_q24[31:24];
    wire [4:0] j = y_q24[23:19];
    wire [18:0] r_q24 = y_q24[18:0];
    // please add tie pipe here
    // Boundary 2: register k, j, r_q24.

    // Stage 3: balanced table selection and first polynomial product.
    wire [24:0] lut_0_0 = 25'd16777216;
    wire [24:0] lut_0_1 = 25'd17144589;
    wire [24:0] lut_0_2 = 25'd17520007;
    wire [24:0] lut_0_3 = 25'd17903645;
    wire [24:0] lut_0_4 = 25'd18295684;
    wire [24:0] lut_0_5 = 25'd18696307;
    wire [24:0] lut_0_6 = 25'd19105703;
    wire [24:0] lut_0_7 = 25'd19524063;
    wire [24:0] lut_0_8 = 25'd19951585;
    wire [24:0] lut_0_9 = 25'd20388467;
    wire [24:0] lut_0_10 = 25'd20834917;
    wire [24:0] lut_0_11 = 25'd21291142;
    wire [24:0] lut_0_12 = 25'd21757357;
    wire [24:0] lut_0_13 = 25'd22233781;
    wire [24:0] lut_0_14 = 25'd22720638;
    wire [24:0] lut_0_15 = 25'd23218155;
    wire [24:0] lut_0_16 = 25'd23726566;
    wire [24:0] lut_0_17 = 25'd24246111;
    wire [24:0] lut_0_18 = 25'd24777031;
    wire [24:0] lut_0_19 = 25'd25319578;
    wire [24:0] lut_0_20 = 25'd25874004;
    wire [24:0] lut_0_21 = 25'd26440571;
    wire [24:0] lut_0_22 = 25'd27019544;
    wire [24:0] lut_0_23 = 25'd27611195;
    wire [24:0] lut_0_24 = 25'd28215802;
    wire [24:0] lut_0_25 = 25'd28833647;
    wire [24:0] lut_0_26 = 25'd29465022;
    wire [24:0] lut_0_27 = 25'd30110222;
    wire [24:0] lut_0_28 = 25'd30769550;
    wire [24:0] lut_0_29 = 25'd31443315;
    wire [24:0] lut_0_30 = 25'd32131834;
    wire [24:0] lut_0_31 = 25'd32835430;
    wire [24:0] lut_1_0 = j[0] ? lut_0_1 : lut_0_0;
    wire [24:0] lut_1_1 = j[0] ? lut_0_3 : lut_0_2;
    wire [24:0] lut_1_2 = j[0] ? lut_0_5 : lut_0_4;
    wire [24:0] lut_1_3 = j[0] ? lut_0_7 : lut_0_6;
    wire [24:0] lut_1_4 = j[0] ? lut_0_9 : lut_0_8;
    wire [24:0] lut_1_5 = j[0] ? lut_0_11 : lut_0_10;
    wire [24:0] lut_1_6 = j[0] ? lut_0_13 : lut_0_12;
    wire [24:0] lut_1_7 = j[0] ? lut_0_15 : lut_0_14;
    wire [24:0] lut_1_8 = j[0] ? lut_0_17 : lut_0_16;
    wire [24:0] lut_1_9 = j[0] ? lut_0_19 : lut_0_18;
    wire [24:0] lut_1_10 = j[0] ? lut_0_21 : lut_0_20;
    wire [24:0] lut_1_11 = j[0] ? lut_0_23 : lut_0_22;
    wire [24:0] lut_1_12 = j[0] ? lut_0_25 : lut_0_24;
    wire [24:0] lut_1_13 = j[0] ? lut_0_27 : lut_0_26;
    wire [24:0] lut_1_14 = j[0] ? lut_0_29 : lut_0_28;
    wire [24:0] lut_1_15 = j[0] ? lut_0_31 : lut_0_30;
    wire [24:0] lut_2_0 = j[1] ? lut_1_1 : lut_1_0;
    wire [24:0] lut_2_1 = j[1] ? lut_1_3 : lut_1_2;
    wire [24:0] lut_2_2 = j[1] ? lut_1_5 : lut_1_4;
    wire [24:0] lut_2_3 = j[1] ? lut_1_7 : lut_1_6;
    wire [24:0] lut_2_4 = j[1] ? lut_1_9 : lut_1_8;
    wire [24:0] lut_2_5 = j[1] ? lut_1_11 : lut_1_10;
    wire [24:0] lut_2_6 = j[1] ? lut_1_13 : lut_1_12;
    wire [24:0] lut_2_7 = j[1] ? lut_1_15 : lut_1_14;
    wire [24:0] lut_3_0 = j[2] ? lut_2_1 : lut_2_0;
    wire [24:0] lut_3_1 = j[2] ? lut_2_3 : lut_2_2;
    wire [24:0] lut_3_2 = j[2] ? lut_2_5 : lut_2_4;
    wire [24:0] lut_3_3 = j[2] ? lut_2_7 : lut_2_6;
    wire [24:0] lut_4_0 = j[3] ? lut_3_1 : lut_3_0;
    wire [24:0] lut_4_1 = j[3] ? lut_3_3 : lut_3_2;
    wire [24:0] lut_5_0 = j[4] ? lut_4_1 : lut_4_0;
    wire [24:0] table_q24 = lut_5_0;
    wire [40:0] c2_product = r_q24 * 22'd4030332;
    wire [16:0] c2_term = c2_product[40:24];
    // please add tie pipe here
    // Boundary 3: register c2_term, table_q24, r_q24, k.

    // Stage 4: ln(2) + r * ln(2)^2/2, Q24.
    wire [23:0] t_q24 = 24'd11629080 + {7'b0, c2_term};
    // please add tie pipe here
    // Boundary 4: register t_q24, table_q24, r_q24, k.

    // Stage 5: h = r * t, Q24; polynomial is 1+h.
    wire [42:0] h_product = r_q24 * t_q24;
    wire [18:0] h_q24 = h_product[42:24];
    // please add tie pipe here
    // Boundary 5: register h_q24, table_q24, k.

    // Stage 6: multiply only the small correction by the table value.
    wire [43:0] correction_product = table_q24 * h_q24;
    wire [19:0] correction_q24 = correction_product[43:24];
    // please add tie pipe here
    // Boundary 6: register correction_q24, table_q24, k.

    // Stage 7: sum, round Q24 to Q23 (ties to even), and pack.
    wire [24:0] mant_q24 = table_q24 + {5'b0, correction_q24};
    wire round_up = mant_q24[0] & mant_q24[1];
    wire [24:0] rounded_sig = {1'b0, mant_q24[24:1]} + {24'b0, round_up};
    wire carry = rounded_sig[24];
    wire [22:0] fraction = carry ? rounded_sig[23:1] : rounded_sig[22:0];
    // Explicit sign-bit replication; modulo-512 addition gives k+127+carry.
    wire [8:0] output_exp = {k[7], k} + 9'd127 + {8'b0, carry};
    assign y = {1'b0, output_exp[7:0], fraction};
    // please add tie pipe here
    // Boundary 7: register y. Seven stages total; II=1. No feedback.
endmodule
`default_nettype wire
