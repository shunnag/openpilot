#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_2637784821013310513) {
   out_2637784821013310513[0] = delta_x[0] + nom_x[0];
   out_2637784821013310513[1] = delta_x[1] + nom_x[1];
   out_2637784821013310513[2] = delta_x[2] + nom_x[2];
   out_2637784821013310513[3] = delta_x[3] + nom_x[3];
   out_2637784821013310513[4] = delta_x[4] + nom_x[4];
   out_2637784821013310513[5] = delta_x[5] + nom_x[5];
   out_2637784821013310513[6] = delta_x[6] + nom_x[6];
   out_2637784821013310513[7] = delta_x[7] + nom_x[7];
   out_2637784821013310513[8] = delta_x[8] + nom_x[8];
   out_2637784821013310513[9] = delta_x[9] + nom_x[9];
   out_2637784821013310513[10] = delta_x[10] + nom_x[10];
   out_2637784821013310513[11] = delta_x[11] + nom_x[11];
   out_2637784821013310513[12] = delta_x[12] + nom_x[12];
   out_2637784821013310513[13] = delta_x[13] + nom_x[13];
   out_2637784821013310513[14] = delta_x[14] + nom_x[14];
   out_2637784821013310513[15] = delta_x[15] + nom_x[15];
   out_2637784821013310513[16] = delta_x[16] + nom_x[16];
   out_2637784821013310513[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_5856550254287827272) {
   out_5856550254287827272[0] = -nom_x[0] + true_x[0];
   out_5856550254287827272[1] = -nom_x[1] + true_x[1];
   out_5856550254287827272[2] = -nom_x[2] + true_x[2];
   out_5856550254287827272[3] = -nom_x[3] + true_x[3];
   out_5856550254287827272[4] = -nom_x[4] + true_x[4];
   out_5856550254287827272[5] = -nom_x[5] + true_x[5];
   out_5856550254287827272[6] = -nom_x[6] + true_x[6];
   out_5856550254287827272[7] = -nom_x[7] + true_x[7];
   out_5856550254287827272[8] = -nom_x[8] + true_x[8];
   out_5856550254287827272[9] = -nom_x[9] + true_x[9];
   out_5856550254287827272[10] = -nom_x[10] + true_x[10];
   out_5856550254287827272[11] = -nom_x[11] + true_x[11];
   out_5856550254287827272[12] = -nom_x[12] + true_x[12];
   out_5856550254287827272[13] = -nom_x[13] + true_x[13];
   out_5856550254287827272[14] = -nom_x[14] + true_x[14];
   out_5856550254287827272[15] = -nom_x[15] + true_x[15];
   out_5856550254287827272[16] = -nom_x[16] + true_x[16];
   out_5856550254287827272[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_3227534214852498246) {
   out_3227534214852498246[0] = 1.0;
   out_3227534214852498246[1] = 0.0;
   out_3227534214852498246[2] = 0.0;
   out_3227534214852498246[3] = 0.0;
   out_3227534214852498246[4] = 0.0;
   out_3227534214852498246[5] = 0.0;
   out_3227534214852498246[6] = 0.0;
   out_3227534214852498246[7] = 0.0;
   out_3227534214852498246[8] = 0.0;
   out_3227534214852498246[9] = 0.0;
   out_3227534214852498246[10] = 0.0;
   out_3227534214852498246[11] = 0.0;
   out_3227534214852498246[12] = 0.0;
   out_3227534214852498246[13] = 0.0;
   out_3227534214852498246[14] = 0.0;
   out_3227534214852498246[15] = 0.0;
   out_3227534214852498246[16] = 0.0;
   out_3227534214852498246[17] = 0.0;
   out_3227534214852498246[18] = 0.0;
   out_3227534214852498246[19] = 1.0;
   out_3227534214852498246[20] = 0.0;
   out_3227534214852498246[21] = 0.0;
   out_3227534214852498246[22] = 0.0;
   out_3227534214852498246[23] = 0.0;
   out_3227534214852498246[24] = 0.0;
   out_3227534214852498246[25] = 0.0;
   out_3227534214852498246[26] = 0.0;
   out_3227534214852498246[27] = 0.0;
   out_3227534214852498246[28] = 0.0;
   out_3227534214852498246[29] = 0.0;
   out_3227534214852498246[30] = 0.0;
   out_3227534214852498246[31] = 0.0;
   out_3227534214852498246[32] = 0.0;
   out_3227534214852498246[33] = 0.0;
   out_3227534214852498246[34] = 0.0;
   out_3227534214852498246[35] = 0.0;
   out_3227534214852498246[36] = 0.0;
   out_3227534214852498246[37] = 0.0;
   out_3227534214852498246[38] = 1.0;
   out_3227534214852498246[39] = 0.0;
   out_3227534214852498246[40] = 0.0;
   out_3227534214852498246[41] = 0.0;
   out_3227534214852498246[42] = 0.0;
   out_3227534214852498246[43] = 0.0;
   out_3227534214852498246[44] = 0.0;
   out_3227534214852498246[45] = 0.0;
   out_3227534214852498246[46] = 0.0;
   out_3227534214852498246[47] = 0.0;
   out_3227534214852498246[48] = 0.0;
   out_3227534214852498246[49] = 0.0;
   out_3227534214852498246[50] = 0.0;
   out_3227534214852498246[51] = 0.0;
   out_3227534214852498246[52] = 0.0;
   out_3227534214852498246[53] = 0.0;
   out_3227534214852498246[54] = 0.0;
   out_3227534214852498246[55] = 0.0;
   out_3227534214852498246[56] = 0.0;
   out_3227534214852498246[57] = 1.0;
   out_3227534214852498246[58] = 0.0;
   out_3227534214852498246[59] = 0.0;
   out_3227534214852498246[60] = 0.0;
   out_3227534214852498246[61] = 0.0;
   out_3227534214852498246[62] = 0.0;
   out_3227534214852498246[63] = 0.0;
   out_3227534214852498246[64] = 0.0;
   out_3227534214852498246[65] = 0.0;
   out_3227534214852498246[66] = 0.0;
   out_3227534214852498246[67] = 0.0;
   out_3227534214852498246[68] = 0.0;
   out_3227534214852498246[69] = 0.0;
   out_3227534214852498246[70] = 0.0;
   out_3227534214852498246[71] = 0.0;
   out_3227534214852498246[72] = 0.0;
   out_3227534214852498246[73] = 0.0;
   out_3227534214852498246[74] = 0.0;
   out_3227534214852498246[75] = 0.0;
   out_3227534214852498246[76] = 1.0;
   out_3227534214852498246[77] = 0.0;
   out_3227534214852498246[78] = 0.0;
   out_3227534214852498246[79] = 0.0;
   out_3227534214852498246[80] = 0.0;
   out_3227534214852498246[81] = 0.0;
   out_3227534214852498246[82] = 0.0;
   out_3227534214852498246[83] = 0.0;
   out_3227534214852498246[84] = 0.0;
   out_3227534214852498246[85] = 0.0;
   out_3227534214852498246[86] = 0.0;
   out_3227534214852498246[87] = 0.0;
   out_3227534214852498246[88] = 0.0;
   out_3227534214852498246[89] = 0.0;
   out_3227534214852498246[90] = 0.0;
   out_3227534214852498246[91] = 0.0;
   out_3227534214852498246[92] = 0.0;
   out_3227534214852498246[93] = 0.0;
   out_3227534214852498246[94] = 0.0;
   out_3227534214852498246[95] = 1.0;
   out_3227534214852498246[96] = 0.0;
   out_3227534214852498246[97] = 0.0;
   out_3227534214852498246[98] = 0.0;
   out_3227534214852498246[99] = 0.0;
   out_3227534214852498246[100] = 0.0;
   out_3227534214852498246[101] = 0.0;
   out_3227534214852498246[102] = 0.0;
   out_3227534214852498246[103] = 0.0;
   out_3227534214852498246[104] = 0.0;
   out_3227534214852498246[105] = 0.0;
   out_3227534214852498246[106] = 0.0;
   out_3227534214852498246[107] = 0.0;
   out_3227534214852498246[108] = 0.0;
   out_3227534214852498246[109] = 0.0;
   out_3227534214852498246[110] = 0.0;
   out_3227534214852498246[111] = 0.0;
   out_3227534214852498246[112] = 0.0;
   out_3227534214852498246[113] = 0.0;
   out_3227534214852498246[114] = 1.0;
   out_3227534214852498246[115] = 0.0;
   out_3227534214852498246[116] = 0.0;
   out_3227534214852498246[117] = 0.0;
   out_3227534214852498246[118] = 0.0;
   out_3227534214852498246[119] = 0.0;
   out_3227534214852498246[120] = 0.0;
   out_3227534214852498246[121] = 0.0;
   out_3227534214852498246[122] = 0.0;
   out_3227534214852498246[123] = 0.0;
   out_3227534214852498246[124] = 0.0;
   out_3227534214852498246[125] = 0.0;
   out_3227534214852498246[126] = 0.0;
   out_3227534214852498246[127] = 0.0;
   out_3227534214852498246[128] = 0.0;
   out_3227534214852498246[129] = 0.0;
   out_3227534214852498246[130] = 0.0;
   out_3227534214852498246[131] = 0.0;
   out_3227534214852498246[132] = 0.0;
   out_3227534214852498246[133] = 1.0;
   out_3227534214852498246[134] = 0.0;
   out_3227534214852498246[135] = 0.0;
   out_3227534214852498246[136] = 0.0;
   out_3227534214852498246[137] = 0.0;
   out_3227534214852498246[138] = 0.0;
   out_3227534214852498246[139] = 0.0;
   out_3227534214852498246[140] = 0.0;
   out_3227534214852498246[141] = 0.0;
   out_3227534214852498246[142] = 0.0;
   out_3227534214852498246[143] = 0.0;
   out_3227534214852498246[144] = 0.0;
   out_3227534214852498246[145] = 0.0;
   out_3227534214852498246[146] = 0.0;
   out_3227534214852498246[147] = 0.0;
   out_3227534214852498246[148] = 0.0;
   out_3227534214852498246[149] = 0.0;
   out_3227534214852498246[150] = 0.0;
   out_3227534214852498246[151] = 0.0;
   out_3227534214852498246[152] = 1.0;
   out_3227534214852498246[153] = 0.0;
   out_3227534214852498246[154] = 0.0;
   out_3227534214852498246[155] = 0.0;
   out_3227534214852498246[156] = 0.0;
   out_3227534214852498246[157] = 0.0;
   out_3227534214852498246[158] = 0.0;
   out_3227534214852498246[159] = 0.0;
   out_3227534214852498246[160] = 0.0;
   out_3227534214852498246[161] = 0.0;
   out_3227534214852498246[162] = 0.0;
   out_3227534214852498246[163] = 0.0;
   out_3227534214852498246[164] = 0.0;
   out_3227534214852498246[165] = 0.0;
   out_3227534214852498246[166] = 0.0;
   out_3227534214852498246[167] = 0.0;
   out_3227534214852498246[168] = 0.0;
   out_3227534214852498246[169] = 0.0;
   out_3227534214852498246[170] = 0.0;
   out_3227534214852498246[171] = 1.0;
   out_3227534214852498246[172] = 0.0;
   out_3227534214852498246[173] = 0.0;
   out_3227534214852498246[174] = 0.0;
   out_3227534214852498246[175] = 0.0;
   out_3227534214852498246[176] = 0.0;
   out_3227534214852498246[177] = 0.0;
   out_3227534214852498246[178] = 0.0;
   out_3227534214852498246[179] = 0.0;
   out_3227534214852498246[180] = 0.0;
   out_3227534214852498246[181] = 0.0;
   out_3227534214852498246[182] = 0.0;
   out_3227534214852498246[183] = 0.0;
   out_3227534214852498246[184] = 0.0;
   out_3227534214852498246[185] = 0.0;
   out_3227534214852498246[186] = 0.0;
   out_3227534214852498246[187] = 0.0;
   out_3227534214852498246[188] = 0.0;
   out_3227534214852498246[189] = 0.0;
   out_3227534214852498246[190] = 1.0;
   out_3227534214852498246[191] = 0.0;
   out_3227534214852498246[192] = 0.0;
   out_3227534214852498246[193] = 0.0;
   out_3227534214852498246[194] = 0.0;
   out_3227534214852498246[195] = 0.0;
   out_3227534214852498246[196] = 0.0;
   out_3227534214852498246[197] = 0.0;
   out_3227534214852498246[198] = 0.0;
   out_3227534214852498246[199] = 0.0;
   out_3227534214852498246[200] = 0.0;
   out_3227534214852498246[201] = 0.0;
   out_3227534214852498246[202] = 0.0;
   out_3227534214852498246[203] = 0.0;
   out_3227534214852498246[204] = 0.0;
   out_3227534214852498246[205] = 0.0;
   out_3227534214852498246[206] = 0.0;
   out_3227534214852498246[207] = 0.0;
   out_3227534214852498246[208] = 0.0;
   out_3227534214852498246[209] = 1.0;
   out_3227534214852498246[210] = 0.0;
   out_3227534214852498246[211] = 0.0;
   out_3227534214852498246[212] = 0.0;
   out_3227534214852498246[213] = 0.0;
   out_3227534214852498246[214] = 0.0;
   out_3227534214852498246[215] = 0.0;
   out_3227534214852498246[216] = 0.0;
   out_3227534214852498246[217] = 0.0;
   out_3227534214852498246[218] = 0.0;
   out_3227534214852498246[219] = 0.0;
   out_3227534214852498246[220] = 0.0;
   out_3227534214852498246[221] = 0.0;
   out_3227534214852498246[222] = 0.0;
   out_3227534214852498246[223] = 0.0;
   out_3227534214852498246[224] = 0.0;
   out_3227534214852498246[225] = 0.0;
   out_3227534214852498246[226] = 0.0;
   out_3227534214852498246[227] = 0.0;
   out_3227534214852498246[228] = 1.0;
   out_3227534214852498246[229] = 0.0;
   out_3227534214852498246[230] = 0.0;
   out_3227534214852498246[231] = 0.0;
   out_3227534214852498246[232] = 0.0;
   out_3227534214852498246[233] = 0.0;
   out_3227534214852498246[234] = 0.0;
   out_3227534214852498246[235] = 0.0;
   out_3227534214852498246[236] = 0.0;
   out_3227534214852498246[237] = 0.0;
   out_3227534214852498246[238] = 0.0;
   out_3227534214852498246[239] = 0.0;
   out_3227534214852498246[240] = 0.0;
   out_3227534214852498246[241] = 0.0;
   out_3227534214852498246[242] = 0.0;
   out_3227534214852498246[243] = 0.0;
   out_3227534214852498246[244] = 0.0;
   out_3227534214852498246[245] = 0.0;
   out_3227534214852498246[246] = 0.0;
   out_3227534214852498246[247] = 1.0;
   out_3227534214852498246[248] = 0.0;
   out_3227534214852498246[249] = 0.0;
   out_3227534214852498246[250] = 0.0;
   out_3227534214852498246[251] = 0.0;
   out_3227534214852498246[252] = 0.0;
   out_3227534214852498246[253] = 0.0;
   out_3227534214852498246[254] = 0.0;
   out_3227534214852498246[255] = 0.0;
   out_3227534214852498246[256] = 0.0;
   out_3227534214852498246[257] = 0.0;
   out_3227534214852498246[258] = 0.0;
   out_3227534214852498246[259] = 0.0;
   out_3227534214852498246[260] = 0.0;
   out_3227534214852498246[261] = 0.0;
   out_3227534214852498246[262] = 0.0;
   out_3227534214852498246[263] = 0.0;
   out_3227534214852498246[264] = 0.0;
   out_3227534214852498246[265] = 0.0;
   out_3227534214852498246[266] = 1.0;
   out_3227534214852498246[267] = 0.0;
   out_3227534214852498246[268] = 0.0;
   out_3227534214852498246[269] = 0.0;
   out_3227534214852498246[270] = 0.0;
   out_3227534214852498246[271] = 0.0;
   out_3227534214852498246[272] = 0.0;
   out_3227534214852498246[273] = 0.0;
   out_3227534214852498246[274] = 0.0;
   out_3227534214852498246[275] = 0.0;
   out_3227534214852498246[276] = 0.0;
   out_3227534214852498246[277] = 0.0;
   out_3227534214852498246[278] = 0.0;
   out_3227534214852498246[279] = 0.0;
   out_3227534214852498246[280] = 0.0;
   out_3227534214852498246[281] = 0.0;
   out_3227534214852498246[282] = 0.0;
   out_3227534214852498246[283] = 0.0;
   out_3227534214852498246[284] = 0.0;
   out_3227534214852498246[285] = 1.0;
   out_3227534214852498246[286] = 0.0;
   out_3227534214852498246[287] = 0.0;
   out_3227534214852498246[288] = 0.0;
   out_3227534214852498246[289] = 0.0;
   out_3227534214852498246[290] = 0.0;
   out_3227534214852498246[291] = 0.0;
   out_3227534214852498246[292] = 0.0;
   out_3227534214852498246[293] = 0.0;
   out_3227534214852498246[294] = 0.0;
   out_3227534214852498246[295] = 0.0;
   out_3227534214852498246[296] = 0.0;
   out_3227534214852498246[297] = 0.0;
   out_3227534214852498246[298] = 0.0;
   out_3227534214852498246[299] = 0.0;
   out_3227534214852498246[300] = 0.0;
   out_3227534214852498246[301] = 0.0;
   out_3227534214852498246[302] = 0.0;
   out_3227534214852498246[303] = 0.0;
   out_3227534214852498246[304] = 1.0;
   out_3227534214852498246[305] = 0.0;
   out_3227534214852498246[306] = 0.0;
   out_3227534214852498246[307] = 0.0;
   out_3227534214852498246[308] = 0.0;
   out_3227534214852498246[309] = 0.0;
   out_3227534214852498246[310] = 0.0;
   out_3227534214852498246[311] = 0.0;
   out_3227534214852498246[312] = 0.0;
   out_3227534214852498246[313] = 0.0;
   out_3227534214852498246[314] = 0.0;
   out_3227534214852498246[315] = 0.0;
   out_3227534214852498246[316] = 0.0;
   out_3227534214852498246[317] = 0.0;
   out_3227534214852498246[318] = 0.0;
   out_3227534214852498246[319] = 0.0;
   out_3227534214852498246[320] = 0.0;
   out_3227534214852498246[321] = 0.0;
   out_3227534214852498246[322] = 0.0;
   out_3227534214852498246[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_4978671403187490301) {
   out_4978671403187490301[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_4978671403187490301[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_4978671403187490301[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_4978671403187490301[3] = dt*state[12] + state[3];
   out_4978671403187490301[4] = dt*state[13] + state[4];
   out_4978671403187490301[5] = dt*state[14] + state[5];
   out_4978671403187490301[6] = state[6];
   out_4978671403187490301[7] = state[7];
   out_4978671403187490301[8] = state[8];
   out_4978671403187490301[9] = state[9];
   out_4978671403187490301[10] = state[10];
   out_4978671403187490301[11] = state[11];
   out_4978671403187490301[12] = state[12];
   out_4978671403187490301[13] = state[13];
   out_4978671403187490301[14] = state[14];
   out_4978671403187490301[15] = state[15];
   out_4978671403187490301[16] = state[16];
   out_4978671403187490301[17] = state[17];
}
void F_fun(double *state, double dt, double *out_5858485075490961391) {
   out_5858485075490961391[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5858485075490961391[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5858485075490961391[2] = 0;
   out_5858485075490961391[3] = 0;
   out_5858485075490961391[4] = 0;
   out_5858485075490961391[5] = 0;
   out_5858485075490961391[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5858485075490961391[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5858485075490961391[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_5858485075490961391[9] = 0;
   out_5858485075490961391[10] = 0;
   out_5858485075490961391[11] = 0;
   out_5858485075490961391[12] = 0;
   out_5858485075490961391[13] = 0;
   out_5858485075490961391[14] = 0;
   out_5858485075490961391[15] = 0;
   out_5858485075490961391[16] = 0;
   out_5858485075490961391[17] = 0;
   out_5858485075490961391[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5858485075490961391[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5858485075490961391[20] = 0;
   out_5858485075490961391[21] = 0;
   out_5858485075490961391[22] = 0;
   out_5858485075490961391[23] = 0;
   out_5858485075490961391[24] = 0;
   out_5858485075490961391[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5858485075490961391[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_5858485075490961391[27] = 0;
   out_5858485075490961391[28] = 0;
   out_5858485075490961391[29] = 0;
   out_5858485075490961391[30] = 0;
   out_5858485075490961391[31] = 0;
   out_5858485075490961391[32] = 0;
   out_5858485075490961391[33] = 0;
   out_5858485075490961391[34] = 0;
   out_5858485075490961391[35] = 0;
   out_5858485075490961391[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5858485075490961391[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5858485075490961391[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5858485075490961391[39] = 0;
   out_5858485075490961391[40] = 0;
   out_5858485075490961391[41] = 0;
   out_5858485075490961391[42] = 0;
   out_5858485075490961391[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5858485075490961391[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_5858485075490961391[45] = 0;
   out_5858485075490961391[46] = 0;
   out_5858485075490961391[47] = 0;
   out_5858485075490961391[48] = 0;
   out_5858485075490961391[49] = 0;
   out_5858485075490961391[50] = 0;
   out_5858485075490961391[51] = 0;
   out_5858485075490961391[52] = 0;
   out_5858485075490961391[53] = 0;
   out_5858485075490961391[54] = 0;
   out_5858485075490961391[55] = 0;
   out_5858485075490961391[56] = 0;
   out_5858485075490961391[57] = 1;
   out_5858485075490961391[58] = 0;
   out_5858485075490961391[59] = 0;
   out_5858485075490961391[60] = 0;
   out_5858485075490961391[61] = 0;
   out_5858485075490961391[62] = 0;
   out_5858485075490961391[63] = 0;
   out_5858485075490961391[64] = 0;
   out_5858485075490961391[65] = 0;
   out_5858485075490961391[66] = dt;
   out_5858485075490961391[67] = 0;
   out_5858485075490961391[68] = 0;
   out_5858485075490961391[69] = 0;
   out_5858485075490961391[70] = 0;
   out_5858485075490961391[71] = 0;
   out_5858485075490961391[72] = 0;
   out_5858485075490961391[73] = 0;
   out_5858485075490961391[74] = 0;
   out_5858485075490961391[75] = 0;
   out_5858485075490961391[76] = 1;
   out_5858485075490961391[77] = 0;
   out_5858485075490961391[78] = 0;
   out_5858485075490961391[79] = 0;
   out_5858485075490961391[80] = 0;
   out_5858485075490961391[81] = 0;
   out_5858485075490961391[82] = 0;
   out_5858485075490961391[83] = 0;
   out_5858485075490961391[84] = 0;
   out_5858485075490961391[85] = dt;
   out_5858485075490961391[86] = 0;
   out_5858485075490961391[87] = 0;
   out_5858485075490961391[88] = 0;
   out_5858485075490961391[89] = 0;
   out_5858485075490961391[90] = 0;
   out_5858485075490961391[91] = 0;
   out_5858485075490961391[92] = 0;
   out_5858485075490961391[93] = 0;
   out_5858485075490961391[94] = 0;
   out_5858485075490961391[95] = 1;
   out_5858485075490961391[96] = 0;
   out_5858485075490961391[97] = 0;
   out_5858485075490961391[98] = 0;
   out_5858485075490961391[99] = 0;
   out_5858485075490961391[100] = 0;
   out_5858485075490961391[101] = 0;
   out_5858485075490961391[102] = 0;
   out_5858485075490961391[103] = 0;
   out_5858485075490961391[104] = dt;
   out_5858485075490961391[105] = 0;
   out_5858485075490961391[106] = 0;
   out_5858485075490961391[107] = 0;
   out_5858485075490961391[108] = 0;
   out_5858485075490961391[109] = 0;
   out_5858485075490961391[110] = 0;
   out_5858485075490961391[111] = 0;
   out_5858485075490961391[112] = 0;
   out_5858485075490961391[113] = 0;
   out_5858485075490961391[114] = 1;
   out_5858485075490961391[115] = 0;
   out_5858485075490961391[116] = 0;
   out_5858485075490961391[117] = 0;
   out_5858485075490961391[118] = 0;
   out_5858485075490961391[119] = 0;
   out_5858485075490961391[120] = 0;
   out_5858485075490961391[121] = 0;
   out_5858485075490961391[122] = 0;
   out_5858485075490961391[123] = 0;
   out_5858485075490961391[124] = 0;
   out_5858485075490961391[125] = 0;
   out_5858485075490961391[126] = 0;
   out_5858485075490961391[127] = 0;
   out_5858485075490961391[128] = 0;
   out_5858485075490961391[129] = 0;
   out_5858485075490961391[130] = 0;
   out_5858485075490961391[131] = 0;
   out_5858485075490961391[132] = 0;
   out_5858485075490961391[133] = 1;
   out_5858485075490961391[134] = 0;
   out_5858485075490961391[135] = 0;
   out_5858485075490961391[136] = 0;
   out_5858485075490961391[137] = 0;
   out_5858485075490961391[138] = 0;
   out_5858485075490961391[139] = 0;
   out_5858485075490961391[140] = 0;
   out_5858485075490961391[141] = 0;
   out_5858485075490961391[142] = 0;
   out_5858485075490961391[143] = 0;
   out_5858485075490961391[144] = 0;
   out_5858485075490961391[145] = 0;
   out_5858485075490961391[146] = 0;
   out_5858485075490961391[147] = 0;
   out_5858485075490961391[148] = 0;
   out_5858485075490961391[149] = 0;
   out_5858485075490961391[150] = 0;
   out_5858485075490961391[151] = 0;
   out_5858485075490961391[152] = 1;
   out_5858485075490961391[153] = 0;
   out_5858485075490961391[154] = 0;
   out_5858485075490961391[155] = 0;
   out_5858485075490961391[156] = 0;
   out_5858485075490961391[157] = 0;
   out_5858485075490961391[158] = 0;
   out_5858485075490961391[159] = 0;
   out_5858485075490961391[160] = 0;
   out_5858485075490961391[161] = 0;
   out_5858485075490961391[162] = 0;
   out_5858485075490961391[163] = 0;
   out_5858485075490961391[164] = 0;
   out_5858485075490961391[165] = 0;
   out_5858485075490961391[166] = 0;
   out_5858485075490961391[167] = 0;
   out_5858485075490961391[168] = 0;
   out_5858485075490961391[169] = 0;
   out_5858485075490961391[170] = 0;
   out_5858485075490961391[171] = 1;
   out_5858485075490961391[172] = 0;
   out_5858485075490961391[173] = 0;
   out_5858485075490961391[174] = 0;
   out_5858485075490961391[175] = 0;
   out_5858485075490961391[176] = 0;
   out_5858485075490961391[177] = 0;
   out_5858485075490961391[178] = 0;
   out_5858485075490961391[179] = 0;
   out_5858485075490961391[180] = 0;
   out_5858485075490961391[181] = 0;
   out_5858485075490961391[182] = 0;
   out_5858485075490961391[183] = 0;
   out_5858485075490961391[184] = 0;
   out_5858485075490961391[185] = 0;
   out_5858485075490961391[186] = 0;
   out_5858485075490961391[187] = 0;
   out_5858485075490961391[188] = 0;
   out_5858485075490961391[189] = 0;
   out_5858485075490961391[190] = 1;
   out_5858485075490961391[191] = 0;
   out_5858485075490961391[192] = 0;
   out_5858485075490961391[193] = 0;
   out_5858485075490961391[194] = 0;
   out_5858485075490961391[195] = 0;
   out_5858485075490961391[196] = 0;
   out_5858485075490961391[197] = 0;
   out_5858485075490961391[198] = 0;
   out_5858485075490961391[199] = 0;
   out_5858485075490961391[200] = 0;
   out_5858485075490961391[201] = 0;
   out_5858485075490961391[202] = 0;
   out_5858485075490961391[203] = 0;
   out_5858485075490961391[204] = 0;
   out_5858485075490961391[205] = 0;
   out_5858485075490961391[206] = 0;
   out_5858485075490961391[207] = 0;
   out_5858485075490961391[208] = 0;
   out_5858485075490961391[209] = 1;
   out_5858485075490961391[210] = 0;
   out_5858485075490961391[211] = 0;
   out_5858485075490961391[212] = 0;
   out_5858485075490961391[213] = 0;
   out_5858485075490961391[214] = 0;
   out_5858485075490961391[215] = 0;
   out_5858485075490961391[216] = 0;
   out_5858485075490961391[217] = 0;
   out_5858485075490961391[218] = 0;
   out_5858485075490961391[219] = 0;
   out_5858485075490961391[220] = 0;
   out_5858485075490961391[221] = 0;
   out_5858485075490961391[222] = 0;
   out_5858485075490961391[223] = 0;
   out_5858485075490961391[224] = 0;
   out_5858485075490961391[225] = 0;
   out_5858485075490961391[226] = 0;
   out_5858485075490961391[227] = 0;
   out_5858485075490961391[228] = 1;
   out_5858485075490961391[229] = 0;
   out_5858485075490961391[230] = 0;
   out_5858485075490961391[231] = 0;
   out_5858485075490961391[232] = 0;
   out_5858485075490961391[233] = 0;
   out_5858485075490961391[234] = 0;
   out_5858485075490961391[235] = 0;
   out_5858485075490961391[236] = 0;
   out_5858485075490961391[237] = 0;
   out_5858485075490961391[238] = 0;
   out_5858485075490961391[239] = 0;
   out_5858485075490961391[240] = 0;
   out_5858485075490961391[241] = 0;
   out_5858485075490961391[242] = 0;
   out_5858485075490961391[243] = 0;
   out_5858485075490961391[244] = 0;
   out_5858485075490961391[245] = 0;
   out_5858485075490961391[246] = 0;
   out_5858485075490961391[247] = 1;
   out_5858485075490961391[248] = 0;
   out_5858485075490961391[249] = 0;
   out_5858485075490961391[250] = 0;
   out_5858485075490961391[251] = 0;
   out_5858485075490961391[252] = 0;
   out_5858485075490961391[253] = 0;
   out_5858485075490961391[254] = 0;
   out_5858485075490961391[255] = 0;
   out_5858485075490961391[256] = 0;
   out_5858485075490961391[257] = 0;
   out_5858485075490961391[258] = 0;
   out_5858485075490961391[259] = 0;
   out_5858485075490961391[260] = 0;
   out_5858485075490961391[261] = 0;
   out_5858485075490961391[262] = 0;
   out_5858485075490961391[263] = 0;
   out_5858485075490961391[264] = 0;
   out_5858485075490961391[265] = 0;
   out_5858485075490961391[266] = 1;
   out_5858485075490961391[267] = 0;
   out_5858485075490961391[268] = 0;
   out_5858485075490961391[269] = 0;
   out_5858485075490961391[270] = 0;
   out_5858485075490961391[271] = 0;
   out_5858485075490961391[272] = 0;
   out_5858485075490961391[273] = 0;
   out_5858485075490961391[274] = 0;
   out_5858485075490961391[275] = 0;
   out_5858485075490961391[276] = 0;
   out_5858485075490961391[277] = 0;
   out_5858485075490961391[278] = 0;
   out_5858485075490961391[279] = 0;
   out_5858485075490961391[280] = 0;
   out_5858485075490961391[281] = 0;
   out_5858485075490961391[282] = 0;
   out_5858485075490961391[283] = 0;
   out_5858485075490961391[284] = 0;
   out_5858485075490961391[285] = 1;
   out_5858485075490961391[286] = 0;
   out_5858485075490961391[287] = 0;
   out_5858485075490961391[288] = 0;
   out_5858485075490961391[289] = 0;
   out_5858485075490961391[290] = 0;
   out_5858485075490961391[291] = 0;
   out_5858485075490961391[292] = 0;
   out_5858485075490961391[293] = 0;
   out_5858485075490961391[294] = 0;
   out_5858485075490961391[295] = 0;
   out_5858485075490961391[296] = 0;
   out_5858485075490961391[297] = 0;
   out_5858485075490961391[298] = 0;
   out_5858485075490961391[299] = 0;
   out_5858485075490961391[300] = 0;
   out_5858485075490961391[301] = 0;
   out_5858485075490961391[302] = 0;
   out_5858485075490961391[303] = 0;
   out_5858485075490961391[304] = 1;
   out_5858485075490961391[305] = 0;
   out_5858485075490961391[306] = 0;
   out_5858485075490961391[307] = 0;
   out_5858485075490961391[308] = 0;
   out_5858485075490961391[309] = 0;
   out_5858485075490961391[310] = 0;
   out_5858485075490961391[311] = 0;
   out_5858485075490961391[312] = 0;
   out_5858485075490961391[313] = 0;
   out_5858485075490961391[314] = 0;
   out_5858485075490961391[315] = 0;
   out_5858485075490961391[316] = 0;
   out_5858485075490961391[317] = 0;
   out_5858485075490961391[318] = 0;
   out_5858485075490961391[319] = 0;
   out_5858485075490961391[320] = 0;
   out_5858485075490961391[321] = 0;
   out_5858485075490961391[322] = 0;
   out_5858485075490961391[323] = 1;
}
void h_4(double *state, double *unused, double *out_1837443762224670303) {
   out_1837443762224670303[0] = state[6] + state[9];
   out_1837443762224670303[1] = state[7] + state[10];
   out_1837443762224670303[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_2620547591899460475) {
   out_2620547591899460475[0] = 0;
   out_2620547591899460475[1] = 0;
   out_2620547591899460475[2] = 0;
   out_2620547591899460475[3] = 0;
   out_2620547591899460475[4] = 0;
   out_2620547591899460475[5] = 0;
   out_2620547591899460475[6] = 1;
   out_2620547591899460475[7] = 0;
   out_2620547591899460475[8] = 0;
   out_2620547591899460475[9] = 1;
   out_2620547591899460475[10] = 0;
   out_2620547591899460475[11] = 0;
   out_2620547591899460475[12] = 0;
   out_2620547591899460475[13] = 0;
   out_2620547591899460475[14] = 0;
   out_2620547591899460475[15] = 0;
   out_2620547591899460475[16] = 0;
   out_2620547591899460475[17] = 0;
   out_2620547591899460475[18] = 0;
   out_2620547591899460475[19] = 0;
   out_2620547591899460475[20] = 0;
   out_2620547591899460475[21] = 0;
   out_2620547591899460475[22] = 0;
   out_2620547591899460475[23] = 0;
   out_2620547591899460475[24] = 0;
   out_2620547591899460475[25] = 1;
   out_2620547591899460475[26] = 0;
   out_2620547591899460475[27] = 0;
   out_2620547591899460475[28] = 1;
   out_2620547591899460475[29] = 0;
   out_2620547591899460475[30] = 0;
   out_2620547591899460475[31] = 0;
   out_2620547591899460475[32] = 0;
   out_2620547591899460475[33] = 0;
   out_2620547591899460475[34] = 0;
   out_2620547591899460475[35] = 0;
   out_2620547591899460475[36] = 0;
   out_2620547591899460475[37] = 0;
   out_2620547591899460475[38] = 0;
   out_2620547591899460475[39] = 0;
   out_2620547591899460475[40] = 0;
   out_2620547591899460475[41] = 0;
   out_2620547591899460475[42] = 0;
   out_2620547591899460475[43] = 0;
   out_2620547591899460475[44] = 1;
   out_2620547591899460475[45] = 0;
   out_2620547591899460475[46] = 0;
   out_2620547591899460475[47] = 1;
   out_2620547591899460475[48] = 0;
   out_2620547591899460475[49] = 0;
   out_2620547591899460475[50] = 0;
   out_2620547591899460475[51] = 0;
   out_2620547591899460475[52] = 0;
   out_2620547591899460475[53] = 0;
}
void h_10(double *state, double *unused, double *out_7143893956583389853) {
   out_7143893956583389853[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_7143893956583389853[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_7143893956583389853[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_8037125999005922999) {
   out_8037125999005922999[0] = 0;
   out_8037125999005922999[1] = 9.8100000000000005*cos(state[1]);
   out_8037125999005922999[2] = 0;
   out_8037125999005922999[3] = 0;
   out_8037125999005922999[4] = -state[8];
   out_8037125999005922999[5] = state[7];
   out_8037125999005922999[6] = 0;
   out_8037125999005922999[7] = state[5];
   out_8037125999005922999[8] = -state[4];
   out_8037125999005922999[9] = 0;
   out_8037125999005922999[10] = 0;
   out_8037125999005922999[11] = 0;
   out_8037125999005922999[12] = 1;
   out_8037125999005922999[13] = 0;
   out_8037125999005922999[14] = 0;
   out_8037125999005922999[15] = 1;
   out_8037125999005922999[16] = 0;
   out_8037125999005922999[17] = 0;
   out_8037125999005922999[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_8037125999005922999[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_8037125999005922999[20] = 0;
   out_8037125999005922999[21] = state[8];
   out_8037125999005922999[22] = 0;
   out_8037125999005922999[23] = -state[6];
   out_8037125999005922999[24] = -state[5];
   out_8037125999005922999[25] = 0;
   out_8037125999005922999[26] = state[3];
   out_8037125999005922999[27] = 0;
   out_8037125999005922999[28] = 0;
   out_8037125999005922999[29] = 0;
   out_8037125999005922999[30] = 0;
   out_8037125999005922999[31] = 1;
   out_8037125999005922999[32] = 0;
   out_8037125999005922999[33] = 0;
   out_8037125999005922999[34] = 1;
   out_8037125999005922999[35] = 0;
   out_8037125999005922999[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_8037125999005922999[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_8037125999005922999[38] = 0;
   out_8037125999005922999[39] = -state[7];
   out_8037125999005922999[40] = state[6];
   out_8037125999005922999[41] = 0;
   out_8037125999005922999[42] = state[4];
   out_8037125999005922999[43] = -state[3];
   out_8037125999005922999[44] = 0;
   out_8037125999005922999[45] = 0;
   out_8037125999005922999[46] = 0;
   out_8037125999005922999[47] = 0;
   out_8037125999005922999[48] = 0;
   out_8037125999005922999[49] = 0;
   out_8037125999005922999[50] = 1;
   out_8037125999005922999[51] = 0;
   out_8037125999005922999[52] = 0;
   out_8037125999005922999[53] = 1;
}
void h_13(double *state, double *unused, double *out_612536517588929158) {
   out_612536517588929158[0] = state[3];
   out_612536517588929158[1] = state[4];
   out_612536517588929158[2] = state[5];
}
void H_13(double *state, double *unused, double *out_591726233432872326) {
   out_591726233432872326[0] = 0;
   out_591726233432872326[1] = 0;
   out_591726233432872326[2] = 0;
   out_591726233432872326[3] = 1;
   out_591726233432872326[4] = 0;
   out_591726233432872326[5] = 0;
   out_591726233432872326[6] = 0;
   out_591726233432872326[7] = 0;
   out_591726233432872326[8] = 0;
   out_591726233432872326[9] = 0;
   out_591726233432872326[10] = 0;
   out_591726233432872326[11] = 0;
   out_591726233432872326[12] = 0;
   out_591726233432872326[13] = 0;
   out_591726233432872326[14] = 0;
   out_591726233432872326[15] = 0;
   out_591726233432872326[16] = 0;
   out_591726233432872326[17] = 0;
   out_591726233432872326[18] = 0;
   out_591726233432872326[19] = 0;
   out_591726233432872326[20] = 0;
   out_591726233432872326[21] = 0;
   out_591726233432872326[22] = 1;
   out_591726233432872326[23] = 0;
   out_591726233432872326[24] = 0;
   out_591726233432872326[25] = 0;
   out_591726233432872326[26] = 0;
   out_591726233432872326[27] = 0;
   out_591726233432872326[28] = 0;
   out_591726233432872326[29] = 0;
   out_591726233432872326[30] = 0;
   out_591726233432872326[31] = 0;
   out_591726233432872326[32] = 0;
   out_591726233432872326[33] = 0;
   out_591726233432872326[34] = 0;
   out_591726233432872326[35] = 0;
   out_591726233432872326[36] = 0;
   out_591726233432872326[37] = 0;
   out_591726233432872326[38] = 0;
   out_591726233432872326[39] = 0;
   out_591726233432872326[40] = 0;
   out_591726233432872326[41] = 1;
   out_591726233432872326[42] = 0;
   out_591726233432872326[43] = 0;
   out_591726233432872326[44] = 0;
   out_591726233432872326[45] = 0;
   out_591726233432872326[46] = 0;
   out_591726233432872326[47] = 0;
   out_591726233432872326[48] = 0;
   out_591726233432872326[49] = 0;
   out_591726233432872326[50] = 0;
   out_591726233432872326[51] = 0;
   out_591726233432872326[52] = 0;
   out_591726233432872326[53] = 0;
}
void h_14(double *state, double *unused, double *out_1327653704680832289) {
   out_1327653704680832289[0] = state[6];
   out_1327653704680832289[1] = state[7];
   out_1327653704680832289[2] = state[8];
}
void H_14(double *state, double *unused, double *out_1342693264440024054) {
   out_1342693264440024054[0] = 0;
   out_1342693264440024054[1] = 0;
   out_1342693264440024054[2] = 0;
   out_1342693264440024054[3] = 0;
   out_1342693264440024054[4] = 0;
   out_1342693264440024054[5] = 0;
   out_1342693264440024054[6] = 1;
   out_1342693264440024054[7] = 0;
   out_1342693264440024054[8] = 0;
   out_1342693264440024054[9] = 0;
   out_1342693264440024054[10] = 0;
   out_1342693264440024054[11] = 0;
   out_1342693264440024054[12] = 0;
   out_1342693264440024054[13] = 0;
   out_1342693264440024054[14] = 0;
   out_1342693264440024054[15] = 0;
   out_1342693264440024054[16] = 0;
   out_1342693264440024054[17] = 0;
   out_1342693264440024054[18] = 0;
   out_1342693264440024054[19] = 0;
   out_1342693264440024054[20] = 0;
   out_1342693264440024054[21] = 0;
   out_1342693264440024054[22] = 0;
   out_1342693264440024054[23] = 0;
   out_1342693264440024054[24] = 0;
   out_1342693264440024054[25] = 1;
   out_1342693264440024054[26] = 0;
   out_1342693264440024054[27] = 0;
   out_1342693264440024054[28] = 0;
   out_1342693264440024054[29] = 0;
   out_1342693264440024054[30] = 0;
   out_1342693264440024054[31] = 0;
   out_1342693264440024054[32] = 0;
   out_1342693264440024054[33] = 0;
   out_1342693264440024054[34] = 0;
   out_1342693264440024054[35] = 0;
   out_1342693264440024054[36] = 0;
   out_1342693264440024054[37] = 0;
   out_1342693264440024054[38] = 0;
   out_1342693264440024054[39] = 0;
   out_1342693264440024054[40] = 0;
   out_1342693264440024054[41] = 0;
   out_1342693264440024054[42] = 0;
   out_1342693264440024054[43] = 0;
   out_1342693264440024054[44] = 1;
   out_1342693264440024054[45] = 0;
   out_1342693264440024054[46] = 0;
   out_1342693264440024054[47] = 0;
   out_1342693264440024054[48] = 0;
   out_1342693264440024054[49] = 0;
   out_1342693264440024054[50] = 0;
   out_1342693264440024054[51] = 0;
   out_1342693264440024054[52] = 0;
   out_1342693264440024054[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_2637784821013310513) {
  err_fun(nom_x, delta_x, out_2637784821013310513);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_5856550254287827272) {
  inv_err_fun(nom_x, true_x, out_5856550254287827272);
}
void pose_H_mod_fun(double *state, double *out_3227534214852498246) {
  H_mod_fun(state, out_3227534214852498246);
}
void pose_f_fun(double *state, double dt, double *out_4978671403187490301) {
  f_fun(state,  dt, out_4978671403187490301);
}
void pose_F_fun(double *state, double dt, double *out_5858485075490961391) {
  F_fun(state,  dt, out_5858485075490961391);
}
void pose_h_4(double *state, double *unused, double *out_1837443762224670303) {
  h_4(state, unused, out_1837443762224670303);
}
void pose_H_4(double *state, double *unused, double *out_2620547591899460475) {
  H_4(state, unused, out_2620547591899460475);
}
void pose_h_10(double *state, double *unused, double *out_7143893956583389853) {
  h_10(state, unused, out_7143893956583389853);
}
void pose_H_10(double *state, double *unused, double *out_8037125999005922999) {
  H_10(state, unused, out_8037125999005922999);
}
void pose_h_13(double *state, double *unused, double *out_612536517588929158) {
  h_13(state, unused, out_612536517588929158);
}
void pose_H_13(double *state, double *unused, double *out_591726233432872326) {
  H_13(state, unused, out_591726233432872326);
}
void pose_h_14(double *state, double *unused, double *out_1327653704680832289) {
  h_14(state, unused, out_1327653704680832289);
}
void pose_H_14(double *state, double *unused, double *out_1342693264440024054) {
  H_14(state, unused, out_1342693264440024054);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
