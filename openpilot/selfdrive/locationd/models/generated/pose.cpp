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
void err_fun(double *nom_x, double *delta_x, double *out_5758895393654592547) {
   out_5758895393654592547[0] = delta_x[0] + nom_x[0];
   out_5758895393654592547[1] = delta_x[1] + nom_x[1];
   out_5758895393654592547[2] = delta_x[2] + nom_x[2];
   out_5758895393654592547[3] = delta_x[3] + nom_x[3];
   out_5758895393654592547[4] = delta_x[4] + nom_x[4];
   out_5758895393654592547[5] = delta_x[5] + nom_x[5];
   out_5758895393654592547[6] = delta_x[6] + nom_x[6];
   out_5758895393654592547[7] = delta_x[7] + nom_x[7];
   out_5758895393654592547[8] = delta_x[8] + nom_x[8];
   out_5758895393654592547[9] = delta_x[9] + nom_x[9];
   out_5758895393654592547[10] = delta_x[10] + nom_x[10];
   out_5758895393654592547[11] = delta_x[11] + nom_x[11];
   out_5758895393654592547[12] = delta_x[12] + nom_x[12];
   out_5758895393654592547[13] = delta_x[13] + nom_x[13];
   out_5758895393654592547[14] = delta_x[14] + nom_x[14];
   out_5758895393654592547[15] = delta_x[15] + nom_x[15];
   out_5758895393654592547[16] = delta_x[16] + nom_x[16];
   out_5758895393654592547[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1226936103861324486) {
   out_1226936103861324486[0] = -nom_x[0] + true_x[0];
   out_1226936103861324486[1] = -nom_x[1] + true_x[1];
   out_1226936103861324486[2] = -nom_x[2] + true_x[2];
   out_1226936103861324486[3] = -nom_x[3] + true_x[3];
   out_1226936103861324486[4] = -nom_x[4] + true_x[4];
   out_1226936103861324486[5] = -nom_x[5] + true_x[5];
   out_1226936103861324486[6] = -nom_x[6] + true_x[6];
   out_1226936103861324486[7] = -nom_x[7] + true_x[7];
   out_1226936103861324486[8] = -nom_x[8] + true_x[8];
   out_1226936103861324486[9] = -nom_x[9] + true_x[9];
   out_1226936103861324486[10] = -nom_x[10] + true_x[10];
   out_1226936103861324486[11] = -nom_x[11] + true_x[11];
   out_1226936103861324486[12] = -nom_x[12] + true_x[12];
   out_1226936103861324486[13] = -nom_x[13] + true_x[13];
   out_1226936103861324486[14] = -nom_x[14] + true_x[14];
   out_1226936103861324486[15] = -nom_x[15] + true_x[15];
   out_1226936103861324486[16] = -nom_x[16] + true_x[16];
   out_1226936103861324486[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_2814892848741251961) {
   out_2814892848741251961[0] = 1.0;
   out_2814892848741251961[1] = 0.0;
   out_2814892848741251961[2] = 0.0;
   out_2814892848741251961[3] = 0.0;
   out_2814892848741251961[4] = 0.0;
   out_2814892848741251961[5] = 0.0;
   out_2814892848741251961[6] = 0.0;
   out_2814892848741251961[7] = 0.0;
   out_2814892848741251961[8] = 0.0;
   out_2814892848741251961[9] = 0.0;
   out_2814892848741251961[10] = 0.0;
   out_2814892848741251961[11] = 0.0;
   out_2814892848741251961[12] = 0.0;
   out_2814892848741251961[13] = 0.0;
   out_2814892848741251961[14] = 0.0;
   out_2814892848741251961[15] = 0.0;
   out_2814892848741251961[16] = 0.0;
   out_2814892848741251961[17] = 0.0;
   out_2814892848741251961[18] = 0.0;
   out_2814892848741251961[19] = 1.0;
   out_2814892848741251961[20] = 0.0;
   out_2814892848741251961[21] = 0.0;
   out_2814892848741251961[22] = 0.0;
   out_2814892848741251961[23] = 0.0;
   out_2814892848741251961[24] = 0.0;
   out_2814892848741251961[25] = 0.0;
   out_2814892848741251961[26] = 0.0;
   out_2814892848741251961[27] = 0.0;
   out_2814892848741251961[28] = 0.0;
   out_2814892848741251961[29] = 0.0;
   out_2814892848741251961[30] = 0.0;
   out_2814892848741251961[31] = 0.0;
   out_2814892848741251961[32] = 0.0;
   out_2814892848741251961[33] = 0.0;
   out_2814892848741251961[34] = 0.0;
   out_2814892848741251961[35] = 0.0;
   out_2814892848741251961[36] = 0.0;
   out_2814892848741251961[37] = 0.0;
   out_2814892848741251961[38] = 1.0;
   out_2814892848741251961[39] = 0.0;
   out_2814892848741251961[40] = 0.0;
   out_2814892848741251961[41] = 0.0;
   out_2814892848741251961[42] = 0.0;
   out_2814892848741251961[43] = 0.0;
   out_2814892848741251961[44] = 0.0;
   out_2814892848741251961[45] = 0.0;
   out_2814892848741251961[46] = 0.0;
   out_2814892848741251961[47] = 0.0;
   out_2814892848741251961[48] = 0.0;
   out_2814892848741251961[49] = 0.0;
   out_2814892848741251961[50] = 0.0;
   out_2814892848741251961[51] = 0.0;
   out_2814892848741251961[52] = 0.0;
   out_2814892848741251961[53] = 0.0;
   out_2814892848741251961[54] = 0.0;
   out_2814892848741251961[55] = 0.0;
   out_2814892848741251961[56] = 0.0;
   out_2814892848741251961[57] = 1.0;
   out_2814892848741251961[58] = 0.0;
   out_2814892848741251961[59] = 0.0;
   out_2814892848741251961[60] = 0.0;
   out_2814892848741251961[61] = 0.0;
   out_2814892848741251961[62] = 0.0;
   out_2814892848741251961[63] = 0.0;
   out_2814892848741251961[64] = 0.0;
   out_2814892848741251961[65] = 0.0;
   out_2814892848741251961[66] = 0.0;
   out_2814892848741251961[67] = 0.0;
   out_2814892848741251961[68] = 0.0;
   out_2814892848741251961[69] = 0.0;
   out_2814892848741251961[70] = 0.0;
   out_2814892848741251961[71] = 0.0;
   out_2814892848741251961[72] = 0.0;
   out_2814892848741251961[73] = 0.0;
   out_2814892848741251961[74] = 0.0;
   out_2814892848741251961[75] = 0.0;
   out_2814892848741251961[76] = 1.0;
   out_2814892848741251961[77] = 0.0;
   out_2814892848741251961[78] = 0.0;
   out_2814892848741251961[79] = 0.0;
   out_2814892848741251961[80] = 0.0;
   out_2814892848741251961[81] = 0.0;
   out_2814892848741251961[82] = 0.0;
   out_2814892848741251961[83] = 0.0;
   out_2814892848741251961[84] = 0.0;
   out_2814892848741251961[85] = 0.0;
   out_2814892848741251961[86] = 0.0;
   out_2814892848741251961[87] = 0.0;
   out_2814892848741251961[88] = 0.0;
   out_2814892848741251961[89] = 0.0;
   out_2814892848741251961[90] = 0.0;
   out_2814892848741251961[91] = 0.0;
   out_2814892848741251961[92] = 0.0;
   out_2814892848741251961[93] = 0.0;
   out_2814892848741251961[94] = 0.0;
   out_2814892848741251961[95] = 1.0;
   out_2814892848741251961[96] = 0.0;
   out_2814892848741251961[97] = 0.0;
   out_2814892848741251961[98] = 0.0;
   out_2814892848741251961[99] = 0.0;
   out_2814892848741251961[100] = 0.0;
   out_2814892848741251961[101] = 0.0;
   out_2814892848741251961[102] = 0.0;
   out_2814892848741251961[103] = 0.0;
   out_2814892848741251961[104] = 0.0;
   out_2814892848741251961[105] = 0.0;
   out_2814892848741251961[106] = 0.0;
   out_2814892848741251961[107] = 0.0;
   out_2814892848741251961[108] = 0.0;
   out_2814892848741251961[109] = 0.0;
   out_2814892848741251961[110] = 0.0;
   out_2814892848741251961[111] = 0.0;
   out_2814892848741251961[112] = 0.0;
   out_2814892848741251961[113] = 0.0;
   out_2814892848741251961[114] = 1.0;
   out_2814892848741251961[115] = 0.0;
   out_2814892848741251961[116] = 0.0;
   out_2814892848741251961[117] = 0.0;
   out_2814892848741251961[118] = 0.0;
   out_2814892848741251961[119] = 0.0;
   out_2814892848741251961[120] = 0.0;
   out_2814892848741251961[121] = 0.0;
   out_2814892848741251961[122] = 0.0;
   out_2814892848741251961[123] = 0.0;
   out_2814892848741251961[124] = 0.0;
   out_2814892848741251961[125] = 0.0;
   out_2814892848741251961[126] = 0.0;
   out_2814892848741251961[127] = 0.0;
   out_2814892848741251961[128] = 0.0;
   out_2814892848741251961[129] = 0.0;
   out_2814892848741251961[130] = 0.0;
   out_2814892848741251961[131] = 0.0;
   out_2814892848741251961[132] = 0.0;
   out_2814892848741251961[133] = 1.0;
   out_2814892848741251961[134] = 0.0;
   out_2814892848741251961[135] = 0.0;
   out_2814892848741251961[136] = 0.0;
   out_2814892848741251961[137] = 0.0;
   out_2814892848741251961[138] = 0.0;
   out_2814892848741251961[139] = 0.0;
   out_2814892848741251961[140] = 0.0;
   out_2814892848741251961[141] = 0.0;
   out_2814892848741251961[142] = 0.0;
   out_2814892848741251961[143] = 0.0;
   out_2814892848741251961[144] = 0.0;
   out_2814892848741251961[145] = 0.0;
   out_2814892848741251961[146] = 0.0;
   out_2814892848741251961[147] = 0.0;
   out_2814892848741251961[148] = 0.0;
   out_2814892848741251961[149] = 0.0;
   out_2814892848741251961[150] = 0.0;
   out_2814892848741251961[151] = 0.0;
   out_2814892848741251961[152] = 1.0;
   out_2814892848741251961[153] = 0.0;
   out_2814892848741251961[154] = 0.0;
   out_2814892848741251961[155] = 0.0;
   out_2814892848741251961[156] = 0.0;
   out_2814892848741251961[157] = 0.0;
   out_2814892848741251961[158] = 0.0;
   out_2814892848741251961[159] = 0.0;
   out_2814892848741251961[160] = 0.0;
   out_2814892848741251961[161] = 0.0;
   out_2814892848741251961[162] = 0.0;
   out_2814892848741251961[163] = 0.0;
   out_2814892848741251961[164] = 0.0;
   out_2814892848741251961[165] = 0.0;
   out_2814892848741251961[166] = 0.0;
   out_2814892848741251961[167] = 0.0;
   out_2814892848741251961[168] = 0.0;
   out_2814892848741251961[169] = 0.0;
   out_2814892848741251961[170] = 0.0;
   out_2814892848741251961[171] = 1.0;
   out_2814892848741251961[172] = 0.0;
   out_2814892848741251961[173] = 0.0;
   out_2814892848741251961[174] = 0.0;
   out_2814892848741251961[175] = 0.0;
   out_2814892848741251961[176] = 0.0;
   out_2814892848741251961[177] = 0.0;
   out_2814892848741251961[178] = 0.0;
   out_2814892848741251961[179] = 0.0;
   out_2814892848741251961[180] = 0.0;
   out_2814892848741251961[181] = 0.0;
   out_2814892848741251961[182] = 0.0;
   out_2814892848741251961[183] = 0.0;
   out_2814892848741251961[184] = 0.0;
   out_2814892848741251961[185] = 0.0;
   out_2814892848741251961[186] = 0.0;
   out_2814892848741251961[187] = 0.0;
   out_2814892848741251961[188] = 0.0;
   out_2814892848741251961[189] = 0.0;
   out_2814892848741251961[190] = 1.0;
   out_2814892848741251961[191] = 0.0;
   out_2814892848741251961[192] = 0.0;
   out_2814892848741251961[193] = 0.0;
   out_2814892848741251961[194] = 0.0;
   out_2814892848741251961[195] = 0.0;
   out_2814892848741251961[196] = 0.0;
   out_2814892848741251961[197] = 0.0;
   out_2814892848741251961[198] = 0.0;
   out_2814892848741251961[199] = 0.0;
   out_2814892848741251961[200] = 0.0;
   out_2814892848741251961[201] = 0.0;
   out_2814892848741251961[202] = 0.0;
   out_2814892848741251961[203] = 0.0;
   out_2814892848741251961[204] = 0.0;
   out_2814892848741251961[205] = 0.0;
   out_2814892848741251961[206] = 0.0;
   out_2814892848741251961[207] = 0.0;
   out_2814892848741251961[208] = 0.0;
   out_2814892848741251961[209] = 1.0;
   out_2814892848741251961[210] = 0.0;
   out_2814892848741251961[211] = 0.0;
   out_2814892848741251961[212] = 0.0;
   out_2814892848741251961[213] = 0.0;
   out_2814892848741251961[214] = 0.0;
   out_2814892848741251961[215] = 0.0;
   out_2814892848741251961[216] = 0.0;
   out_2814892848741251961[217] = 0.0;
   out_2814892848741251961[218] = 0.0;
   out_2814892848741251961[219] = 0.0;
   out_2814892848741251961[220] = 0.0;
   out_2814892848741251961[221] = 0.0;
   out_2814892848741251961[222] = 0.0;
   out_2814892848741251961[223] = 0.0;
   out_2814892848741251961[224] = 0.0;
   out_2814892848741251961[225] = 0.0;
   out_2814892848741251961[226] = 0.0;
   out_2814892848741251961[227] = 0.0;
   out_2814892848741251961[228] = 1.0;
   out_2814892848741251961[229] = 0.0;
   out_2814892848741251961[230] = 0.0;
   out_2814892848741251961[231] = 0.0;
   out_2814892848741251961[232] = 0.0;
   out_2814892848741251961[233] = 0.0;
   out_2814892848741251961[234] = 0.0;
   out_2814892848741251961[235] = 0.0;
   out_2814892848741251961[236] = 0.0;
   out_2814892848741251961[237] = 0.0;
   out_2814892848741251961[238] = 0.0;
   out_2814892848741251961[239] = 0.0;
   out_2814892848741251961[240] = 0.0;
   out_2814892848741251961[241] = 0.0;
   out_2814892848741251961[242] = 0.0;
   out_2814892848741251961[243] = 0.0;
   out_2814892848741251961[244] = 0.0;
   out_2814892848741251961[245] = 0.0;
   out_2814892848741251961[246] = 0.0;
   out_2814892848741251961[247] = 1.0;
   out_2814892848741251961[248] = 0.0;
   out_2814892848741251961[249] = 0.0;
   out_2814892848741251961[250] = 0.0;
   out_2814892848741251961[251] = 0.0;
   out_2814892848741251961[252] = 0.0;
   out_2814892848741251961[253] = 0.0;
   out_2814892848741251961[254] = 0.0;
   out_2814892848741251961[255] = 0.0;
   out_2814892848741251961[256] = 0.0;
   out_2814892848741251961[257] = 0.0;
   out_2814892848741251961[258] = 0.0;
   out_2814892848741251961[259] = 0.0;
   out_2814892848741251961[260] = 0.0;
   out_2814892848741251961[261] = 0.0;
   out_2814892848741251961[262] = 0.0;
   out_2814892848741251961[263] = 0.0;
   out_2814892848741251961[264] = 0.0;
   out_2814892848741251961[265] = 0.0;
   out_2814892848741251961[266] = 1.0;
   out_2814892848741251961[267] = 0.0;
   out_2814892848741251961[268] = 0.0;
   out_2814892848741251961[269] = 0.0;
   out_2814892848741251961[270] = 0.0;
   out_2814892848741251961[271] = 0.0;
   out_2814892848741251961[272] = 0.0;
   out_2814892848741251961[273] = 0.0;
   out_2814892848741251961[274] = 0.0;
   out_2814892848741251961[275] = 0.0;
   out_2814892848741251961[276] = 0.0;
   out_2814892848741251961[277] = 0.0;
   out_2814892848741251961[278] = 0.0;
   out_2814892848741251961[279] = 0.0;
   out_2814892848741251961[280] = 0.0;
   out_2814892848741251961[281] = 0.0;
   out_2814892848741251961[282] = 0.0;
   out_2814892848741251961[283] = 0.0;
   out_2814892848741251961[284] = 0.0;
   out_2814892848741251961[285] = 1.0;
   out_2814892848741251961[286] = 0.0;
   out_2814892848741251961[287] = 0.0;
   out_2814892848741251961[288] = 0.0;
   out_2814892848741251961[289] = 0.0;
   out_2814892848741251961[290] = 0.0;
   out_2814892848741251961[291] = 0.0;
   out_2814892848741251961[292] = 0.0;
   out_2814892848741251961[293] = 0.0;
   out_2814892848741251961[294] = 0.0;
   out_2814892848741251961[295] = 0.0;
   out_2814892848741251961[296] = 0.0;
   out_2814892848741251961[297] = 0.0;
   out_2814892848741251961[298] = 0.0;
   out_2814892848741251961[299] = 0.0;
   out_2814892848741251961[300] = 0.0;
   out_2814892848741251961[301] = 0.0;
   out_2814892848741251961[302] = 0.0;
   out_2814892848741251961[303] = 0.0;
   out_2814892848741251961[304] = 1.0;
   out_2814892848741251961[305] = 0.0;
   out_2814892848741251961[306] = 0.0;
   out_2814892848741251961[307] = 0.0;
   out_2814892848741251961[308] = 0.0;
   out_2814892848741251961[309] = 0.0;
   out_2814892848741251961[310] = 0.0;
   out_2814892848741251961[311] = 0.0;
   out_2814892848741251961[312] = 0.0;
   out_2814892848741251961[313] = 0.0;
   out_2814892848741251961[314] = 0.0;
   out_2814892848741251961[315] = 0.0;
   out_2814892848741251961[316] = 0.0;
   out_2814892848741251961[317] = 0.0;
   out_2814892848741251961[318] = 0.0;
   out_2814892848741251961[319] = 0.0;
   out_2814892848741251961[320] = 0.0;
   out_2814892848741251961[321] = 0.0;
   out_2814892848741251961[322] = 0.0;
   out_2814892848741251961[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_8661001625037563019) {
   out_8661001625037563019[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_8661001625037563019[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_8661001625037563019[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_8661001625037563019[3] = dt*state[12] + state[3];
   out_8661001625037563019[4] = dt*state[13] + state[4];
   out_8661001625037563019[5] = dt*state[14] + state[5];
   out_8661001625037563019[6] = state[6];
   out_8661001625037563019[7] = state[7];
   out_8661001625037563019[8] = state[8];
   out_8661001625037563019[9] = state[9];
   out_8661001625037563019[10] = state[10];
   out_8661001625037563019[11] = state[11];
   out_8661001625037563019[12] = state[12];
   out_8661001625037563019[13] = state[13];
   out_8661001625037563019[14] = state[14];
   out_8661001625037563019[15] = state[15];
   out_8661001625037563019[16] = state[16];
   out_8661001625037563019[17] = state[17];
}
void F_fun(double *state, double dt, double *out_8260004715325140458) {
   out_8260004715325140458[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_8260004715325140458[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_8260004715325140458[2] = 0;
   out_8260004715325140458[3] = 0;
   out_8260004715325140458[4] = 0;
   out_8260004715325140458[5] = 0;
   out_8260004715325140458[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_8260004715325140458[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_8260004715325140458[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_8260004715325140458[9] = 0;
   out_8260004715325140458[10] = 0;
   out_8260004715325140458[11] = 0;
   out_8260004715325140458[12] = 0;
   out_8260004715325140458[13] = 0;
   out_8260004715325140458[14] = 0;
   out_8260004715325140458[15] = 0;
   out_8260004715325140458[16] = 0;
   out_8260004715325140458[17] = 0;
   out_8260004715325140458[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_8260004715325140458[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_8260004715325140458[20] = 0;
   out_8260004715325140458[21] = 0;
   out_8260004715325140458[22] = 0;
   out_8260004715325140458[23] = 0;
   out_8260004715325140458[24] = 0;
   out_8260004715325140458[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_8260004715325140458[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_8260004715325140458[27] = 0;
   out_8260004715325140458[28] = 0;
   out_8260004715325140458[29] = 0;
   out_8260004715325140458[30] = 0;
   out_8260004715325140458[31] = 0;
   out_8260004715325140458[32] = 0;
   out_8260004715325140458[33] = 0;
   out_8260004715325140458[34] = 0;
   out_8260004715325140458[35] = 0;
   out_8260004715325140458[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_8260004715325140458[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_8260004715325140458[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_8260004715325140458[39] = 0;
   out_8260004715325140458[40] = 0;
   out_8260004715325140458[41] = 0;
   out_8260004715325140458[42] = 0;
   out_8260004715325140458[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_8260004715325140458[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_8260004715325140458[45] = 0;
   out_8260004715325140458[46] = 0;
   out_8260004715325140458[47] = 0;
   out_8260004715325140458[48] = 0;
   out_8260004715325140458[49] = 0;
   out_8260004715325140458[50] = 0;
   out_8260004715325140458[51] = 0;
   out_8260004715325140458[52] = 0;
   out_8260004715325140458[53] = 0;
   out_8260004715325140458[54] = 0;
   out_8260004715325140458[55] = 0;
   out_8260004715325140458[56] = 0;
   out_8260004715325140458[57] = 1;
   out_8260004715325140458[58] = 0;
   out_8260004715325140458[59] = 0;
   out_8260004715325140458[60] = 0;
   out_8260004715325140458[61] = 0;
   out_8260004715325140458[62] = 0;
   out_8260004715325140458[63] = 0;
   out_8260004715325140458[64] = 0;
   out_8260004715325140458[65] = 0;
   out_8260004715325140458[66] = dt;
   out_8260004715325140458[67] = 0;
   out_8260004715325140458[68] = 0;
   out_8260004715325140458[69] = 0;
   out_8260004715325140458[70] = 0;
   out_8260004715325140458[71] = 0;
   out_8260004715325140458[72] = 0;
   out_8260004715325140458[73] = 0;
   out_8260004715325140458[74] = 0;
   out_8260004715325140458[75] = 0;
   out_8260004715325140458[76] = 1;
   out_8260004715325140458[77] = 0;
   out_8260004715325140458[78] = 0;
   out_8260004715325140458[79] = 0;
   out_8260004715325140458[80] = 0;
   out_8260004715325140458[81] = 0;
   out_8260004715325140458[82] = 0;
   out_8260004715325140458[83] = 0;
   out_8260004715325140458[84] = 0;
   out_8260004715325140458[85] = dt;
   out_8260004715325140458[86] = 0;
   out_8260004715325140458[87] = 0;
   out_8260004715325140458[88] = 0;
   out_8260004715325140458[89] = 0;
   out_8260004715325140458[90] = 0;
   out_8260004715325140458[91] = 0;
   out_8260004715325140458[92] = 0;
   out_8260004715325140458[93] = 0;
   out_8260004715325140458[94] = 0;
   out_8260004715325140458[95] = 1;
   out_8260004715325140458[96] = 0;
   out_8260004715325140458[97] = 0;
   out_8260004715325140458[98] = 0;
   out_8260004715325140458[99] = 0;
   out_8260004715325140458[100] = 0;
   out_8260004715325140458[101] = 0;
   out_8260004715325140458[102] = 0;
   out_8260004715325140458[103] = 0;
   out_8260004715325140458[104] = dt;
   out_8260004715325140458[105] = 0;
   out_8260004715325140458[106] = 0;
   out_8260004715325140458[107] = 0;
   out_8260004715325140458[108] = 0;
   out_8260004715325140458[109] = 0;
   out_8260004715325140458[110] = 0;
   out_8260004715325140458[111] = 0;
   out_8260004715325140458[112] = 0;
   out_8260004715325140458[113] = 0;
   out_8260004715325140458[114] = 1;
   out_8260004715325140458[115] = 0;
   out_8260004715325140458[116] = 0;
   out_8260004715325140458[117] = 0;
   out_8260004715325140458[118] = 0;
   out_8260004715325140458[119] = 0;
   out_8260004715325140458[120] = 0;
   out_8260004715325140458[121] = 0;
   out_8260004715325140458[122] = 0;
   out_8260004715325140458[123] = 0;
   out_8260004715325140458[124] = 0;
   out_8260004715325140458[125] = 0;
   out_8260004715325140458[126] = 0;
   out_8260004715325140458[127] = 0;
   out_8260004715325140458[128] = 0;
   out_8260004715325140458[129] = 0;
   out_8260004715325140458[130] = 0;
   out_8260004715325140458[131] = 0;
   out_8260004715325140458[132] = 0;
   out_8260004715325140458[133] = 1;
   out_8260004715325140458[134] = 0;
   out_8260004715325140458[135] = 0;
   out_8260004715325140458[136] = 0;
   out_8260004715325140458[137] = 0;
   out_8260004715325140458[138] = 0;
   out_8260004715325140458[139] = 0;
   out_8260004715325140458[140] = 0;
   out_8260004715325140458[141] = 0;
   out_8260004715325140458[142] = 0;
   out_8260004715325140458[143] = 0;
   out_8260004715325140458[144] = 0;
   out_8260004715325140458[145] = 0;
   out_8260004715325140458[146] = 0;
   out_8260004715325140458[147] = 0;
   out_8260004715325140458[148] = 0;
   out_8260004715325140458[149] = 0;
   out_8260004715325140458[150] = 0;
   out_8260004715325140458[151] = 0;
   out_8260004715325140458[152] = 1;
   out_8260004715325140458[153] = 0;
   out_8260004715325140458[154] = 0;
   out_8260004715325140458[155] = 0;
   out_8260004715325140458[156] = 0;
   out_8260004715325140458[157] = 0;
   out_8260004715325140458[158] = 0;
   out_8260004715325140458[159] = 0;
   out_8260004715325140458[160] = 0;
   out_8260004715325140458[161] = 0;
   out_8260004715325140458[162] = 0;
   out_8260004715325140458[163] = 0;
   out_8260004715325140458[164] = 0;
   out_8260004715325140458[165] = 0;
   out_8260004715325140458[166] = 0;
   out_8260004715325140458[167] = 0;
   out_8260004715325140458[168] = 0;
   out_8260004715325140458[169] = 0;
   out_8260004715325140458[170] = 0;
   out_8260004715325140458[171] = 1;
   out_8260004715325140458[172] = 0;
   out_8260004715325140458[173] = 0;
   out_8260004715325140458[174] = 0;
   out_8260004715325140458[175] = 0;
   out_8260004715325140458[176] = 0;
   out_8260004715325140458[177] = 0;
   out_8260004715325140458[178] = 0;
   out_8260004715325140458[179] = 0;
   out_8260004715325140458[180] = 0;
   out_8260004715325140458[181] = 0;
   out_8260004715325140458[182] = 0;
   out_8260004715325140458[183] = 0;
   out_8260004715325140458[184] = 0;
   out_8260004715325140458[185] = 0;
   out_8260004715325140458[186] = 0;
   out_8260004715325140458[187] = 0;
   out_8260004715325140458[188] = 0;
   out_8260004715325140458[189] = 0;
   out_8260004715325140458[190] = 1;
   out_8260004715325140458[191] = 0;
   out_8260004715325140458[192] = 0;
   out_8260004715325140458[193] = 0;
   out_8260004715325140458[194] = 0;
   out_8260004715325140458[195] = 0;
   out_8260004715325140458[196] = 0;
   out_8260004715325140458[197] = 0;
   out_8260004715325140458[198] = 0;
   out_8260004715325140458[199] = 0;
   out_8260004715325140458[200] = 0;
   out_8260004715325140458[201] = 0;
   out_8260004715325140458[202] = 0;
   out_8260004715325140458[203] = 0;
   out_8260004715325140458[204] = 0;
   out_8260004715325140458[205] = 0;
   out_8260004715325140458[206] = 0;
   out_8260004715325140458[207] = 0;
   out_8260004715325140458[208] = 0;
   out_8260004715325140458[209] = 1;
   out_8260004715325140458[210] = 0;
   out_8260004715325140458[211] = 0;
   out_8260004715325140458[212] = 0;
   out_8260004715325140458[213] = 0;
   out_8260004715325140458[214] = 0;
   out_8260004715325140458[215] = 0;
   out_8260004715325140458[216] = 0;
   out_8260004715325140458[217] = 0;
   out_8260004715325140458[218] = 0;
   out_8260004715325140458[219] = 0;
   out_8260004715325140458[220] = 0;
   out_8260004715325140458[221] = 0;
   out_8260004715325140458[222] = 0;
   out_8260004715325140458[223] = 0;
   out_8260004715325140458[224] = 0;
   out_8260004715325140458[225] = 0;
   out_8260004715325140458[226] = 0;
   out_8260004715325140458[227] = 0;
   out_8260004715325140458[228] = 1;
   out_8260004715325140458[229] = 0;
   out_8260004715325140458[230] = 0;
   out_8260004715325140458[231] = 0;
   out_8260004715325140458[232] = 0;
   out_8260004715325140458[233] = 0;
   out_8260004715325140458[234] = 0;
   out_8260004715325140458[235] = 0;
   out_8260004715325140458[236] = 0;
   out_8260004715325140458[237] = 0;
   out_8260004715325140458[238] = 0;
   out_8260004715325140458[239] = 0;
   out_8260004715325140458[240] = 0;
   out_8260004715325140458[241] = 0;
   out_8260004715325140458[242] = 0;
   out_8260004715325140458[243] = 0;
   out_8260004715325140458[244] = 0;
   out_8260004715325140458[245] = 0;
   out_8260004715325140458[246] = 0;
   out_8260004715325140458[247] = 1;
   out_8260004715325140458[248] = 0;
   out_8260004715325140458[249] = 0;
   out_8260004715325140458[250] = 0;
   out_8260004715325140458[251] = 0;
   out_8260004715325140458[252] = 0;
   out_8260004715325140458[253] = 0;
   out_8260004715325140458[254] = 0;
   out_8260004715325140458[255] = 0;
   out_8260004715325140458[256] = 0;
   out_8260004715325140458[257] = 0;
   out_8260004715325140458[258] = 0;
   out_8260004715325140458[259] = 0;
   out_8260004715325140458[260] = 0;
   out_8260004715325140458[261] = 0;
   out_8260004715325140458[262] = 0;
   out_8260004715325140458[263] = 0;
   out_8260004715325140458[264] = 0;
   out_8260004715325140458[265] = 0;
   out_8260004715325140458[266] = 1;
   out_8260004715325140458[267] = 0;
   out_8260004715325140458[268] = 0;
   out_8260004715325140458[269] = 0;
   out_8260004715325140458[270] = 0;
   out_8260004715325140458[271] = 0;
   out_8260004715325140458[272] = 0;
   out_8260004715325140458[273] = 0;
   out_8260004715325140458[274] = 0;
   out_8260004715325140458[275] = 0;
   out_8260004715325140458[276] = 0;
   out_8260004715325140458[277] = 0;
   out_8260004715325140458[278] = 0;
   out_8260004715325140458[279] = 0;
   out_8260004715325140458[280] = 0;
   out_8260004715325140458[281] = 0;
   out_8260004715325140458[282] = 0;
   out_8260004715325140458[283] = 0;
   out_8260004715325140458[284] = 0;
   out_8260004715325140458[285] = 1;
   out_8260004715325140458[286] = 0;
   out_8260004715325140458[287] = 0;
   out_8260004715325140458[288] = 0;
   out_8260004715325140458[289] = 0;
   out_8260004715325140458[290] = 0;
   out_8260004715325140458[291] = 0;
   out_8260004715325140458[292] = 0;
   out_8260004715325140458[293] = 0;
   out_8260004715325140458[294] = 0;
   out_8260004715325140458[295] = 0;
   out_8260004715325140458[296] = 0;
   out_8260004715325140458[297] = 0;
   out_8260004715325140458[298] = 0;
   out_8260004715325140458[299] = 0;
   out_8260004715325140458[300] = 0;
   out_8260004715325140458[301] = 0;
   out_8260004715325140458[302] = 0;
   out_8260004715325140458[303] = 0;
   out_8260004715325140458[304] = 1;
   out_8260004715325140458[305] = 0;
   out_8260004715325140458[306] = 0;
   out_8260004715325140458[307] = 0;
   out_8260004715325140458[308] = 0;
   out_8260004715325140458[309] = 0;
   out_8260004715325140458[310] = 0;
   out_8260004715325140458[311] = 0;
   out_8260004715325140458[312] = 0;
   out_8260004715325140458[313] = 0;
   out_8260004715325140458[314] = 0;
   out_8260004715325140458[315] = 0;
   out_8260004715325140458[316] = 0;
   out_8260004715325140458[317] = 0;
   out_8260004715325140458[318] = 0;
   out_8260004715325140458[319] = 0;
   out_8260004715325140458[320] = 0;
   out_8260004715325140458[321] = 0;
   out_8260004715325140458[322] = 0;
   out_8260004715325140458[323] = 1;
}
void h_4(double *state, double *unused, double *out_6076013284157106490) {
   out_6076013284157106490[0] = state[6] + state[9];
   out_6076013284157106490[1] = state[7] + state[10];
   out_6076013284157106490[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_1616945366858353857) {
   out_1616945366858353857[0] = 0;
   out_1616945366858353857[1] = 0;
   out_1616945366858353857[2] = 0;
   out_1616945366858353857[3] = 0;
   out_1616945366858353857[4] = 0;
   out_1616945366858353857[5] = 0;
   out_1616945366858353857[6] = 1;
   out_1616945366858353857[7] = 0;
   out_1616945366858353857[8] = 0;
   out_1616945366858353857[9] = 1;
   out_1616945366858353857[10] = 0;
   out_1616945366858353857[11] = 0;
   out_1616945366858353857[12] = 0;
   out_1616945366858353857[13] = 0;
   out_1616945366858353857[14] = 0;
   out_1616945366858353857[15] = 0;
   out_1616945366858353857[16] = 0;
   out_1616945366858353857[17] = 0;
   out_1616945366858353857[18] = 0;
   out_1616945366858353857[19] = 0;
   out_1616945366858353857[20] = 0;
   out_1616945366858353857[21] = 0;
   out_1616945366858353857[22] = 0;
   out_1616945366858353857[23] = 0;
   out_1616945366858353857[24] = 0;
   out_1616945366858353857[25] = 1;
   out_1616945366858353857[26] = 0;
   out_1616945366858353857[27] = 0;
   out_1616945366858353857[28] = 1;
   out_1616945366858353857[29] = 0;
   out_1616945366858353857[30] = 0;
   out_1616945366858353857[31] = 0;
   out_1616945366858353857[32] = 0;
   out_1616945366858353857[33] = 0;
   out_1616945366858353857[34] = 0;
   out_1616945366858353857[35] = 0;
   out_1616945366858353857[36] = 0;
   out_1616945366858353857[37] = 0;
   out_1616945366858353857[38] = 0;
   out_1616945366858353857[39] = 0;
   out_1616945366858353857[40] = 0;
   out_1616945366858353857[41] = 0;
   out_1616945366858353857[42] = 0;
   out_1616945366858353857[43] = 0;
   out_1616945366858353857[44] = 1;
   out_1616945366858353857[45] = 0;
   out_1616945366858353857[46] = 0;
   out_1616945366858353857[47] = 1;
   out_1616945366858353857[48] = 0;
   out_1616945366858353857[49] = 0;
   out_1616945366858353857[50] = 0;
   out_1616945366858353857[51] = 0;
   out_1616945366858353857[52] = 0;
   out_1616945366858353857[53] = 0;
}
void h_10(double *state, double *unused, double *out_4519099356584783039) {
   out_4519099356584783039[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_4519099356584783039[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_4519099356584783039[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_6862378656678310006) {
   out_6862378656678310006[0] = 0;
   out_6862378656678310006[1] = 9.8100000000000005*cos(state[1]);
   out_6862378656678310006[2] = 0;
   out_6862378656678310006[3] = 0;
   out_6862378656678310006[4] = -state[8];
   out_6862378656678310006[5] = state[7];
   out_6862378656678310006[6] = 0;
   out_6862378656678310006[7] = state[5];
   out_6862378656678310006[8] = -state[4];
   out_6862378656678310006[9] = 0;
   out_6862378656678310006[10] = 0;
   out_6862378656678310006[11] = 0;
   out_6862378656678310006[12] = 1;
   out_6862378656678310006[13] = 0;
   out_6862378656678310006[14] = 0;
   out_6862378656678310006[15] = 1;
   out_6862378656678310006[16] = 0;
   out_6862378656678310006[17] = 0;
   out_6862378656678310006[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_6862378656678310006[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_6862378656678310006[20] = 0;
   out_6862378656678310006[21] = state[8];
   out_6862378656678310006[22] = 0;
   out_6862378656678310006[23] = -state[6];
   out_6862378656678310006[24] = -state[5];
   out_6862378656678310006[25] = 0;
   out_6862378656678310006[26] = state[3];
   out_6862378656678310006[27] = 0;
   out_6862378656678310006[28] = 0;
   out_6862378656678310006[29] = 0;
   out_6862378656678310006[30] = 0;
   out_6862378656678310006[31] = 1;
   out_6862378656678310006[32] = 0;
   out_6862378656678310006[33] = 0;
   out_6862378656678310006[34] = 1;
   out_6862378656678310006[35] = 0;
   out_6862378656678310006[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_6862378656678310006[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_6862378656678310006[38] = 0;
   out_6862378656678310006[39] = -state[7];
   out_6862378656678310006[40] = state[6];
   out_6862378656678310006[41] = 0;
   out_6862378656678310006[42] = state[4];
   out_6862378656678310006[43] = -state[3];
   out_6862378656678310006[44] = 0;
   out_6862378656678310006[45] = 0;
   out_6862378656678310006[46] = 0;
   out_6862378656678310006[47] = 0;
   out_6862378656678310006[48] = 0;
   out_6862378656678310006[49] = 0;
   out_6862378656678310006[50] = 1;
   out_6862378656678310006[51] = 0;
   out_6862378656678310006[52] = 0;
   out_6862378656678310006[53] = 1;
}
void h_13(double *state, double *unused, double *out_7637538022978350115) {
   out_7637538022978350115[0] = state[3];
   out_7637538022978350115[1] = state[4];
   out_7637538022978350115[2] = state[5];
}
void H_13(double *state, double *unused, double *out_1595328458473978944) {
   out_1595328458473978944[0] = 0;
   out_1595328458473978944[1] = 0;
   out_1595328458473978944[2] = 0;
   out_1595328458473978944[3] = 1;
   out_1595328458473978944[4] = 0;
   out_1595328458473978944[5] = 0;
   out_1595328458473978944[6] = 0;
   out_1595328458473978944[7] = 0;
   out_1595328458473978944[8] = 0;
   out_1595328458473978944[9] = 0;
   out_1595328458473978944[10] = 0;
   out_1595328458473978944[11] = 0;
   out_1595328458473978944[12] = 0;
   out_1595328458473978944[13] = 0;
   out_1595328458473978944[14] = 0;
   out_1595328458473978944[15] = 0;
   out_1595328458473978944[16] = 0;
   out_1595328458473978944[17] = 0;
   out_1595328458473978944[18] = 0;
   out_1595328458473978944[19] = 0;
   out_1595328458473978944[20] = 0;
   out_1595328458473978944[21] = 0;
   out_1595328458473978944[22] = 1;
   out_1595328458473978944[23] = 0;
   out_1595328458473978944[24] = 0;
   out_1595328458473978944[25] = 0;
   out_1595328458473978944[26] = 0;
   out_1595328458473978944[27] = 0;
   out_1595328458473978944[28] = 0;
   out_1595328458473978944[29] = 0;
   out_1595328458473978944[30] = 0;
   out_1595328458473978944[31] = 0;
   out_1595328458473978944[32] = 0;
   out_1595328458473978944[33] = 0;
   out_1595328458473978944[34] = 0;
   out_1595328458473978944[35] = 0;
   out_1595328458473978944[36] = 0;
   out_1595328458473978944[37] = 0;
   out_1595328458473978944[38] = 0;
   out_1595328458473978944[39] = 0;
   out_1595328458473978944[40] = 0;
   out_1595328458473978944[41] = 1;
   out_1595328458473978944[42] = 0;
   out_1595328458473978944[43] = 0;
   out_1595328458473978944[44] = 0;
   out_1595328458473978944[45] = 0;
   out_1595328458473978944[46] = 0;
   out_1595328458473978944[47] = 0;
   out_1595328458473978944[48] = 0;
   out_1595328458473978944[49] = 0;
   out_1595328458473978944[50] = 0;
   out_1595328458473978944[51] = 0;
   out_1595328458473978944[52] = 0;
   out_1595328458473978944[53] = 0;
}
void h_14(double *state, double *unused, double *out_7888116198887489293) {
   out_7888116198887489293[0] = state[6];
   out_7888116198887489293[1] = state[7];
   out_7888116198887489293[2] = state[8];
}
void H_14(double *state, double *unused, double *out_4699733799153726153) {
   out_4699733799153726153[0] = 0;
   out_4699733799153726153[1] = 0;
   out_4699733799153726153[2] = 0;
   out_4699733799153726153[3] = 0;
   out_4699733799153726153[4] = 0;
   out_4699733799153726153[5] = 0;
   out_4699733799153726153[6] = 1;
   out_4699733799153726153[7] = 0;
   out_4699733799153726153[8] = 0;
   out_4699733799153726153[9] = 0;
   out_4699733799153726153[10] = 0;
   out_4699733799153726153[11] = 0;
   out_4699733799153726153[12] = 0;
   out_4699733799153726153[13] = 0;
   out_4699733799153726153[14] = 0;
   out_4699733799153726153[15] = 0;
   out_4699733799153726153[16] = 0;
   out_4699733799153726153[17] = 0;
   out_4699733799153726153[18] = 0;
   out_4699733799153726153[19] = 0;
   out_4699733799153726153[20] = 0;
   out_4699733799153726153[21] = 0;
   out_4699733799153726153[22] = 0;
   out_4699733799153726153[23] = 0;
   out_4699733799153726153[24] = 0;
   out_4699733799153726153[25] = 1;
   out_4699733799153726153[26] = 0;
   out_4699733799153726153[27] = 0;
   out_4699733799153726153[28] = 0;
   out_4699733799153726153[29] = 0;
   out_4699733799153726153[30] = 0;
   out_4699733799153726153[31] = 0;
   out_4699733799153726153[32] = 0;
   out_4699733799153726153[33] = 0;
   out_4699733799153726153[34] = 0;
   out_4699733799153726153[35] = 0;
   out_4699733799153726153[36] = 0;
   out_4699733799153726153[37] = 0;
   out_4699733799153726153[38] = 0;
   out_4699733799153726153[39] = 0;
   out_4699733799153726153[40] = 0;
   out_4699733799153726153[41] = 0;
   out_4699733799153726153[42] = 0;
   out_4699733799153726153[43] = 0;
   out_4699733799153726153[44] = 1;
   out_4699733799153726153[45] = 0;
   out_4699733799153726153[46] = 0;
   out_4699733799153726153[47] = 0;
   out_4699733799153726153[48] = 0;
   out_4699733799153726153[49] = 0;
   out_4699733799153726153[50] = 0;
   out_4699733799153726153[51] = 0;
   out_4699733799153726153[52] = 0;
   out_4699733799153726153[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_5758895393654592547) {
  err_fun(nom_x, delta_x, out_5758895393654592547);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1226936103861324486) {
  inv_err_fun(nom_x, true_x, out_1226936103861324486);
}
void pose_H_mod_fun(double *state, double *out_2814892848741251961) {
  H_mod_fun(state, out_2814892848741251961);
}
void pose_f_fun(double *state, double dt, double *out_8661001625037563019) {
  f_fun(state,  dt, out_8661001625037563019);
}
void pose_F_fun(double *state, double dt, double *out_8260004715325140458) {
  F_fun(state,  dt, out_8260004715325140458);
}
void pose_h_4(double *state, double *unused, double *out_6076013284157106490) {
  h_4(state, unused, out_6076013284157106490);
}
void pose_H_4(double *state, double *unused, double *out_1616945366858353857) {
  H_4(state, unused, out_1616945366858353857);
}
void pose_h_10(double *state, double *unused, double *out_4519099356584783039) {
  h_10(state, unused, out_4519099356584783039);
}
void pose_H_10(double *state, double *unused, double *out_6862378656678310006) {
  H_10(state, unused, out_6862378656678310006);
}
void pose_h_13(double *state, double *unused, double *out_7637538022978350115) {
  h_13(state, unused, out_7637538022978350115);
}
void pose_H_13(double *state, double *unused, double *out_1595328458473978944) {
  H_13(state, unused, out_1595328458473978944);
}
void pose_h_14(double *state, double *unused, double *out_7888116198887489293) {
  h_14(state, unused, out_7888116198887489293);
}
void pose_H_14(double *state, double *unused, double *out_4699733799153726153) {
  H_14(state, unused, out_4699733799153726153);
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
