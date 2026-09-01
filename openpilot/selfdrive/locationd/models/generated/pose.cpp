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
void err_fun(double *nom_x, double *delta_x, double *out_377710204961129279) {
   out_377710204961129279[0] = delta_x[0] + nom_x[0];
   out_377710204961129279[1] = delta_x[1] + nom_x[1];
   out_377710204961129279[2] = delta_x[2] + nom_x[2];
   out_377710204961129279[3] = delta_x[3] + nom_x[3];
   out_377710204961129279[4] = delta_x[4] + nom_x[4];
   out_377710204961129279[5] = delta_x[5] + nom_x[5];
   out_377710204961129279[6] = delta_x[6] + nom_x[6];
   out_377710204961129279[7] = delta_x[7] + nom_x[7];
   out_377710204961129279[8] = delta_x[8] + nom_x[8];
   out_377710204961129279[9] = delta_x[9] + nom_x[9];
   out_377710204961129279[10] = delta_x[10] + nom_x[10];
   out_377710204961129279[11] = delta_x[11] + nom_x[11];
   out_377710204961129279[12] = delta_x[12] + nom_x[12];
   out_377710204961129279[13] = delta_x[13] + nom_x[13];
   out_377710204961129279[14] = delta_x[14] + nom_x[14];
   out_377710204961129279[15] = delta_x[15] + nom_x[15];
   out_377710204961129279[16] = delta_x[16] + nom_x[16];
   out_377710204961129279[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_2728279097657860545) {
   out_2728279097657860545[0] = -nom_x[0] + true_x[0];
   out_2728279097657860545[1] = -nom_x[1] + true_x[1];
   out_2728279097657860545[2] = -nom_x[2] + true_x[2];
   out_2728279097657860545[3] = -nom_x[3] + true_x[3];
   out_2728279097657860545[4] = -nom_x[4] + true_x[4];
   out_2728279097657860545[5] = -nom_x[5] + true_x[5];
   out_2728279097657860545[6] = -nom_x[6] + true_x[6];
   out_2728279097657860545[7] = -nom_x[7] + true_x[7];
   out_2728279097657860545[8] = -nom_x[8] + true_x[8];
   out_2728279097657860545[9] = -nom_x[9] + true_x[9];
   out_2728279097657860545[10] = -nom_x[10] + true_x[10];
   out_2728279097657860545[11] = -nom_x[11] + true_x[11];
   out_2728279097657860545[12] = -nom_x[12] + true_x[12];
   out_2728279097657860545[13] = -nom_x[13] + true_x[13];
   out_2728279097657860545[14] = -nom_x[14] + true_x[14];
   out_2728279097657860545[15] = -nom_x[15] + true_x[15];
   out_2728279097657860545[16] = -nom_x[16] + true_x[16];
   out_2728279097657860545[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_8995624703004407813) {
   out_8995624703004407813[0] = 1.0;
   out_8995624703004407813[1] = 0.0;
   out_8995624703004407813[2] = 0.0;
   out_8995624703004407813[3] = 0.0;
   out_8995624703004407813[4] = 0.0;
   out_8995624703004407813[5] = 0.0;
   out_8995624703004407813[6] = 0.0;
   out_8995624703004407813[7] = 0.0;
   out_8995624703004407813[8] = 0.0;
   out_8995624703004407813[9] = 0.0;
   out_8995624703004407813[10] = 0.0;
   out_8995624703004407813[11] = 0.0;
   out_8995624703004407813[12] = 0.0;
   out_8995624703004407813[13] = 0.0;
   out_8995624703004407813[14] = 0.0;
   out_8995624703004407813[15] = 0.0;
   out_8995624703004407813[16] = 0.0;
   out_8995624703004407813[17] = 0.0;
   out_8995624703004407813[18] = 0.0;
   out_8995624703004407813[19] = 1.0;
   out_8995624703004407813[20] = 0.0;
   out_8995624703004407813[21] = 0.0;
   out_8995624703004407813[22] = 0.0;
   out_8995624703004407813[23] = 0.0;
   out_8995624703004407813[24] = 0.0;
   out_8995624703004407813[25] = 0.0;
   out_8995624703004407813[26] = 0.0;
   out_8995624703004407813[27] = 0.0;
   out_8995624703004407813[28] = 0.0;
   out_8995624703004407813[29] = 0.0;
   out_8995624703004407813[30] = 0.0;
   out_8995624703004407813[31] = 0.0;
   out_8995624703004407813[32] = 0.0;
   out_8995624703004407813[33] = 0.0;
   out_8995624703004407813[34] = 0.0;
   out_8995624703004407813[35] = 0.0;
   out_8995624703004407813[36] = 0.0;
   out_8995624703004407813[37] = 0.0;
   out_8995624703004407813[38] = 1.0;
   out_8995624703004407813[39] = 0.0;
   out_8995624703004407813[40] = 0.0;
   out_8995624703004407813[41] = 0.0;
   out_8995624703004407813[42] = 0.0;
   out_8995624703004407813[43] = 0.0;
   out_8995624703004407813[44] = 0.0;
   out_8995624703004407813[45] = 0.0;
   out_8995624703004407813[46] = 0.0;
   out_8995624703004407813[47] = 0.0;
   out_8995624703004407813[48] = 0.0;
   out_8995624703004407813[49] = 0.0;
   out_8995624703004407813[50] = 0.0;
   out_8995624703004407813[51] = 0.0;
   out_8995624703004407813[52] = 0.0;
   out_8995624703004407813[53] = 0.0;
   out_8995624703004407813[54] = 0.0;
   out_8995624703004407813[55] = 0.0;
   out_8995624703004407813[56] = 0.0;
   out_8995624703004407813[57] = 1.0;
   out_8995624703004407813[58] = 0.0;
   out_8995624703004407813[59] = 0.0;
   out_8995624703004407813[60] = 0.0;
   out_8995624703004407813[61] = 0.0;
   out_8995624703004407813[62] = 0.0;
   out_8995624703004407813[63] = 0.0;
   out_8995624703004407813[64] = 0.0;
   out_8995624703004407813[65] = 0.0;
   out_8995624703004407813[66] = 0.0;
   out_8995624703004407813[67] = 0.0;
   out_8995624703004407813[68] = 0.0;
   out_8995624703004407813[69] = 0.0;
   out_8995624703004407813[70] = 0.0;
   out_8995624703004407813[71] = 0.0;
   out_8995624703004407813[72] = 0.0;
   out_8995624703004407813[73] = 0.0;
   out_8995624703004407813[74] = 0.0;
   out_8995624703004407813[75] = 0.0;
   out_8995624703004407813[76] = 1.0;
   out_8995624703004407813[77] = 0.0;
   out_8995624703004407813[78] = 0.0;
   out_8995624703004407813[79] = 0.0;
   out_8995624703004407813[80] = 0.0;
   out_8995624703004407813[81] = 0.0;
   out_8995624703004407813[82] = 0.0;
   out_8995624703004407813[83] = 0.0;
   out_8995624703004407813[84] = 0.0;
   out_8995624703004407813[85] = 0.0;
   out_8995624703004407813[86] = 0.0;
   out_8995624703004407813[87] = 0.0;
   out_8995624703004407813[88] = 0.0;
   out_8995624703004407813[89] = 0.0;
   out_8995624703004407813[90] = 0.0;
   out_8995624703004407813[91] = 0.0;
   out_8995624703004407813[92] = 0.0;
   out_8995624703004407813[93] = 0.0;
   out_8995624703004407813[94] = 0.0;
   out_8995624703004407813[95] = 1.0;
   out_8995624703004407813[96] = 0.0;
   out_8995624703004407813[97] = 0.0;
   out_8995624703004407813[98] = 0.0;
   out_8995624703004407813[99] = 0.0;
   out_8995624703004407813[100] = 0.0;
   out_8995624703004407813[101] = 0.0;
   out_8995624703004407813[102] = 0.0;
   out_8995624703004407813[103] = 0.0;
   out_8995624703004407813[104] = 0.0;
   out_8995624703004407813[105] = 0.0;
   out_8995624703004407813[106] = 0.0;
   out_8995624703004407813[107] = 0.0;
   out_8995624703004407813[108] = 0.0;
   out_8995624703004407813[109] = 0.0;
   out_8995624703004407813[110] = 0.0;
   out_8995624703004407813[111] = 0.0;
   out_8995624703004407813[112] = 0.0;
   out_8995624703004407813[113] = 0.0;
   out_8995624703004407813[114] = 1.0;
   out_8995624703004407813[115] = 0.0;
   out_8995624703004407813[116] = 0.0;
   out_8995624703004407813[117] = 0.0;
   out_8995624703004407813[118] = 0.0;
   out_8995624703004407813[119] = 0.0;
   out_8995624703004407813[120] = 0.0;
   out_8995624703004407813[121] = 0.0;
   out_8995624703004407813[122] = 0.0;
   out_8995624703004407813[123] = 0.0;
   out_8995624703004407813[124] = 0.0;
   out_8995624703004407813[125] = 0.0;
   out_8995624703004407813[126] = 0.0;
   out_8995624703004407813[127] = 0.0;
   out_8995624703004407813[128] = 0.0;
   out_8995624703004407813[129] = 0.0;
   out_8995624703004407813[130] = 0.0;
   out_8995624703004407813[131] = 0.0;
   out_8995624703004407813[132] = 0.0;
   out_8995624703004407813[133] = 1.0;
   out_8995624703004407813[134] = 0.0;
   out_8995624703004407813[135] = 0.0;
   out_8995624703004407813[136] = 0.0;
   out_8995624703004407813[137] = 0.0;
   out_8995624703004407813[138] = 0.0;
   out_8995624703004407813[139] = 0.0;
   out_8995624703004407813[140] = 0.0;
   out_8995624703004407813[141] = 0.0;
   out_8995624703004407813[142] = 0.0;
   out_8995624703004407813[143] = 0.0;
   out_8995624703004407813[144] = 0.0;
   out_8995624703004407813[145] = 0.0;
   out_8995624703004407813[146] = 0.0;
   out_8995624703004407813[147] = 0.0;
   out_8995624703004407813[148] = 0.0;
   out_8995624703004407813[149] = 0.0;
   out_8995624703004407813[150] = 0.0;
   out_8995624703004407813[151] = 0.0;
   out_8995624703004407813[152] = 1.0;
   out_8995624703004407813[153] = 0.0;
   out_8995624703004407813[154] = 0.0;
   out_8995624703004407813[155] = 0.0;
   out_8995624703004407813[156] = 0.0;
   out_8995624703004407813[157] = 0.0;
   out_8995624703004407813[158] = 0.0;
   out_8995624703004407813[159] = 0.0;
   out_8995624703004407813[160] = 0.0;
   out_8995624703004407813[161] = 0.0;
   out_8995624703004407813[162] = 0.0;
   out_8995624703004407813[163] = 0.0;
   out_8995624703004407813[164] = 0.0;
   out_8995624703004407813[165] = 0.0;
   out_8995624703004407813[166] = 0.0;
   out_8995624703004407813[167] = 0.0;
   out_8995624703004407813[168] = 0.0;
   out_8995624703004407813[169] = 0.0;
   out_8995624703004407813[170] = 0.0;
   out_8995624703004407813[171] = 1.0;
   out_8995624703004407813[172] = 0.0;
   out_8995624703004407813[173] = 0.0;
   out_8995624703004407813[174] = 0.0;
   out_8995624703004407813[175] = 0.0;
   out_8995624703004407813[176] = 0.0;
   out_8995624703004407813[177] = 0.0;
   out_8995624703004407813[178] = 0.0;
   out_8995624703004407813[179] = 0.0;
   out_8995624703004407813[180] = 0.0;
   out_8995624703004407813[181] = 0.0;
   out_8995624703004407813[182] = 0.0;
   out_8995624703004407813[183] = 0.0;
   out_8995624703004407813[184] = 0.0;
   out_8995624703004407813[185] = 0.0;
   out_8995624703004407813[186] = 0.0;
   out_8995624703004407813[187] = 0.0;
   out_8995624703004407813[188] = 0.0;
   out_8995624703004407813[189] = 0.0;
   out_8995624703004407813[190] = 1.0;
   out_8995624703004407813[191] = 0.0;
   out_8995624703004407813[192] = 0.0;
   out_8995624703004407813[193] = 0.0;
   out_8995624703004407813[194] = 0.0;
   out_8995624703004407813[195] = 0.0;
   out_8995624703004407813[196] = 0.0;
   out_8995624703004407813[197] = 0.0;
   out_8995624703004407813[198] = 0.0;
   out_8995624703004407813[199] = 0.0;
   out_8995624703004407813[200] = 0.0;
   out_8995624703004407813[201] = 0.0;
   out_8995624703004407813[202] = 0.0;
   out_8995624703004407813[203] = 0.0;
   out_8995624703004407813[204] = 0.0;
   out_8995624703004407813[205] = 0.0;
   out_8995624703004407813[206] = 0.0;
   out_8995624703004407813[207] = 0.0;
   out_8995624703004407813[208] = 0.0;
   out_8995624703004407813[209] = 1.0;
   out_8995624703004407813[210] = 0.0;
   out_8995624703004407813[211] = 0.0;
   out_8995624703004407813[212] = 0.0;
   out_8995624703004407813[213] = 0.0;
   out_8995624703004407813[214] = 0.0;
   out_8995624703004407813[215] = 0.0;
   out_8995624703004407813[216] = 0.0;
   out_8995624703004407813[217] = 0.0;
   out_8995624703004407813[218] = 0.0;
   out_8995624703004407813[219] = 0.0;
   out_8995624703004407813[220] = 0.0;
   out_8995624703004407813[221] = 0.0;
   out_8995624703004407813[222] = 0.0;
   out_8995624703004407813[223] = 0.0;
   out_8995624703004407813[224] = 0.0;
   out_8995624703004407813[225] = 0.0;
   out_8995624703004407813[226] = 0.0;
   out_8995624703004407813[227] = 0.0;
   out_8995624703004407813[228] = 1.0;
   out_8995624703004407813[229] = 0.0;
   out_8995624703004407813[230] = 0.0;
   out_8995624703004407813[231] = 0.0;
   out_8995624703004407813[232] = 0.0;
   out_8995624703004407813[233] = 0.0;
   out_8995624703004407813[234] = 0.0;
   out_8995624703004407813[235] = 0.0;
   out_8995624703004407813[236] = 0.0;
   out_8995624703004407813[237] = 0.0;
   out_8995624703004407813[238] = 0.0;
   out_8995624703004407813[239] = 0.0;
   out_8995624703004407813[240] = 0.0;
   out_8995624703004407813[241] = 0.0;
   out_8995624703004407813[242] = 0.0;
   out_8995624703004407813[243] = 0.0;
   out_8995624703004407813[244] = 0.0;
   out_8995624703004407813[245] = 0.0;
   out_8995624703004407813[246] = 0.0;
   out_8995624703004407813[247] = 1.0;
   out_8995624703004407813[248] = 0.0;
   out_8995624703004407813[249] = 0.0;
   out_8995624703004407813[250] = 0.0;
   out_8995624703004407813[251] = 0.0;
   out_8995624703004407813[252] = 0.0;
   out_8995624703004407813[253] = 0.0;
   out_8995624703004407813[254] = 0.0;
   out_8995624703004407813[255] = 0.0;
   out_8995624703004407813[256] = 0.0;
   out_8995624703004407813[257] = 0.0;
   out_8995624703004407813[258] = 0.0;
   out_8995624703004407813[259] = 0.0;
   out_8995624703004407813[260] = 0.0;
   out_8995624703004407813[261] = 0.0;
   out_8995624703004407813[262] = 0.0;
   out_8995624703004407813[263] = 0.0;
   out_8995624703004407813[264] = 0.0;
   out_8995624703004407813[265] = 0.0;
   out_8995624703004407813[266] = 1.0;
   out_8995624703004407813[267] = 0.0;
   out_8995624703004407813[268] = 0.0;
   out_8995624703004407813[269] = 0.0;
   out_8995624703004407813[270] = 0.0;
   out_8995624703004407813[271] = 0.0;
   out_8995624703004407813[272] = 0.0;
   out_8995624703004407813[273] = 0.0;
   out_8995624703004407813[274] = 0.0;
   out_8995624703004407813[275] = 0.0;
   out_8995624703004407813[276] = 0.0;
   out_8995624703004407813[277] = 0.0;
   out_8995624703004407813[278] = 0.0;
   out_8995624703004407813[279] = 0.0;
   out_8995624703004407813[280] = 0.0;
   out_8995624703004407813[281] = 0.0;
   out_8995624703004407813[282] = 0.0;
   out_8995624703004407813[283] = 0.0;
   out_8995624703004407813[284] = 0.0;
   out_8995624703004407813[285] = 1.0;
   out_8995624703004407813[286] = 0.0;
   out_8995624703004407813[287] = 0.0;
   out_8995624703004407813[288] = 0.0;
   out_8995624703004407813[289] = 0.0;
   out_8995624703004407813[290] = 0.0;
   out_8995624703004407813[291] = 0.0;
   out_8995624703004407813[292] = 0.0;
   out_8995624703004407813[293] = 0.0;
   out_8995624703004407813[294] = 0.0;
   out_8995624703004407813[295] = 0.0;
   out_8995624703004407813[296] = 0.0;
   out_8995624703004407813[297] = 0.0;
   out_8995624703004407813[298] = 0.0;
   out_8995624703004407813[299] = 0.0;
   out_8995624703004407813[300] = 0.0;
   out_8995624703004407813[301] = 0.0;
   out_8995624703004407813[302] = 0.0;
   out_8995624703004407813[303] = 0.0;
   out_8995624703004407813[304] = 1.0;
   out_8995624703004407813[305] = 0.0;
   out_8995624703004407813[306] = 0.0;
   out_8995624703004407813[307] = 0.0;
   out_8995624703004407813[308] = 0.0;
   out_8995624703004407813[309] = 0.0;
   out_8995624703004407813[310] = 0.0;
   out_8995624703004407813[311] = 0.0;
   out_8995624703004407813[312] = 0.0;
   out_8995624703004407813[313] = 0.0;
   out_8995624703004407813[314] = 0.0;
   out_8995624703004407813[315] = 0.0;
   out_8995624703004407813[316] = 0.0;
   out_8995624703004407813[317] = 0.0;
   out_8995624703004407813[318] = 0.0;
   out_8995624703004407813[319] = 0.0;
   out_8995624703004407813[320] = 0.0;
   out_8995624703004407813[321] = 0.0;
   out_8995624703004407813[322] = 0.0;
   out_8995624703004407813[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_4645218274869152611) {
   out_4645218274869152611[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_4645218274869152611[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_4645218274869152611[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_4645218274869152611[3] = dt*state[12] + state[3];
   out_4645218274869152611[4] = dt*state[13] + state[4];
   out_4645218274869152611[5] = dt*state[14] + state[5];
   out_4645218274869152611[6] = state[6];
   out_4645218274869152611[7] = state[7];
   out_4645218274869152611[8] = state[8];
   out_4645218274869152611[9] = state[9];
   out_4645218274869152611[10] = state[10];
   out_4645218274869152611[11] = state[11];
   out_4645218274869152611[12] = state[12];
   out_4645218274869152611[13] = state[13];
   out_4645218274869152611[14] = state[14];
   out_4645218274869152611[15] = state[15];
   out_4645218274869152611[16] = state[16];
   out_4645218274869152611[17] = state[17];
}
void F_fun(double *state, double dt, double *out_548560934011257004) {
   out_548560934011257004[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_548560934011257004[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_548560934011257004[2] = 0;
   out_548560934011257004[3] = 0;
   out_548560934011257004[4] = 0;
   out_548560934011257004[5] = 0;
   out_548560934011257004[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_548560934011257004[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_548560934011257004[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_548560934011257004[9] = 0;
   out_548560934011257004[10] = 0;
   out_548560934011257004[11] = 0;
   out_548560934011257004[12] = 0;
   out_548560934011257004[13] = 0;
   out_548560934011257004[14] = 0;
   out_548560934011257004[15] = 0;
   out_548560934011257004[16] = 0;
   out_548560934011257004[17] = 0;
   out_548560934011257004[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_548560934011257004[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_548560934011257004[20] = 0;
   out_548560934011257004[21] = 0;
   out_548560934011257004[22] = 0;
   out_548560934011257004[23] = 0;
   out_548560934011257004[24] = 0;
   out_548560934011257004[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_548560934011257004[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_548560934011257004[27] = 0;
   out_548560934011257004[28] = 0;
   out_548560934011257004[29] = 0;
   out_548560934011257004[30] = 0;
   out_548560934011257004[31] = 0;
   out_548560934011257004[32] = 0;
   out_548560934011257004[33] = 0;
   out_548560934011257004[34] = 0;
   out_548560934011257004[35] = 0;
   out_548560934011257004[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_548560934011257004[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_548560934011257004[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_548560934011257004[39] = 0;
   out_548560934011257004[40] = 0;
   out_548560934011257004[41] = 0;
   out_548560934011257004[42] = 0;
   out_548560934011257004[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_548560934011257004[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_548560934011257004[45] = 0;
   out_548560934011257004[46] = 0;
   out_548560934011257004[47] = 0;
   out_548560934011257004[48] = 0;
   out_548560934011257004[49] = 0;
   out_548560934011257004[50] = 0;
   out_548560934011257004[51] = 0;
   out_548560934011257004[52] = 0;
   out_548560934011257004[53] = 0;
   out_548560934011257004[54] = 0;
   out_548560934011257004[55] = 0;
   out_548560934011257004[56] = 0;
   out_548560934011257004[57] = 1;
   out_548560934011257004[58] = 0;
   out_548560934011257004[59] = 0;
   out_548560934011257004[60] = 0;
   out_548560934011257004[61] = 0;
   out_548560934011257004[62] = 0;
   out_548560934011257004[63] = 0;
   out_548560934011257004[64] = 0;
   out_548560934011257004[65] = 0;
   out_548560934011257004[66] = dt;
   out_548560934011257004[67] = 0;
   out_548560934011257004[68] = 0;
   out_548560934011257004[69] = 0;
   out_548560934011257004[70] = 0;
   out_548560934011257004[71] = 0;
   out_548560934011257004[72] = 0;
   out_548560934011257004[73] = 0;
   out_548560934011257004[74] = 0;
   out_548560934011257004[75] = 0;
   out_548560934011257004[76] = 1;
   out_548560934011257004[77] = 0;
   out_548560934011257004[78] = 0;
   out_548560934011257004[79] = 0;
   out_548560934011257004[80] = 0;
   out_548560934011257004[81] = 0;
   out_548560934011257004[82] = 0;
   out_548560934011257004[83] = 0;
   out_548560934011257004[84] = 0;
   out_548560934011257004[85] = dt;
   out_548560934011257004[86] = 0;
   out_548560934011257004[87] = 0;
   out_548560934011257004[88] = 0;
   out_548560934011257004[89] = 0;
   out_548560934011257004[90] = 0;
   out_548560934011257004[91] = 0;
   out_548560934011257004[92] = 0;
   out_548560934011257004[93] = 0;
   out_548560934011257004[94] = 0;
   out_548560934011257004[95] = 1;
   out_548560934011257004[96] = 0;
   out_548560934011257004[97] = 0;
   out_548560934011257004[98] = 0;
   out_548560934011257004[99] = 0;
   out_548560934011257004[100] = 0;
   out_548560934011257004[101] = 0;
   out_548560934011257004[102] = 0;
   out_548560934011257004[103] = 0;
   out_548560934011257004[104] = dt;
   out_548560934011257004[105] = 0;
   out_548560934011257004[106] = 0;
   out_548560934011257004[107] = 0;
   out_548560934011257004[108] = 0;
   out_548560934011257004[109] = 0;
   out_548560934011257004[110] = 0;
   out_548560934011257004[111] = 0;
   out_548560934011257004[112] = 0;
   out_548560934011257004[113] = 0;
   out_548560934011257004[114] = 1;
   out_548560934011257004[115] = 0;
   out_548560934011257004[116] = 0;
   out_548560934011257004[117] = 0;
   out_548560934011257004[118] = 0;
   out_548560934011257004[119] = 0;
   out_548560934011257004[120] = 0;
   out_548560934011257004[121] = 0;
   out_548560934011257004[122] = 0;
   out_548560934011257004[123] = 0;
   out_548560934011257004[124] = 0;
   out_548560934011257004[125] = 0;
   out_548560934011257004[126] = 0;
   out_548560934011257004[127] = 0;
   out_548560934011257004[128] = 0;
   out_548560934011257004[129] = 0;
   out_548560934011257004[130] = 0;
   out_548560934011257004[131] = 0;
   out_548560934011257004[132] = 0;
   out_548560934011257004[133] = 1;
   out_548560934011257004[134] = 0;
   out_548560934011257004[135] = 0;
   out_548560934011257004[136] = 0;
   out_548560934011257004[137] = 0;
   out_548560934011257004[138] = 0;
   out_548560934011257004[139] = 0;
   out_548560934011257004[140] = 0;
   out_548560934011257004[141] = 0;
   out_548560934011257004[142] = 0;
   out_548560934011257004[143] = 0;
   out_548560934011257004[144] = 0;
   out_548560934011257004[145] = 0;
   out_548560934011257004[146] = 0;
   out_548560934011257004[147] = 0;
   out_548560934011257004[148] = 0;
   out_548560934011257004[149] = 0;
   out_548560934011257004[150] = 0;
   out_548560934011257004[151] = 0;
   out_548560934011257004[152] = 1;
   out_548560934011257004[153] = 0;
   out_548560934011257004[154] = 0;
   out_548560934011257004[155] = 0;
   out_548560934011257004[156] = 0;
   out_548560934011257004[157] = 0;
   out_548560934011257004[158] = 0;
   out_548560934011257004[159] = 0;
   out_548560934011257004[160] = 0;
   out_548560934011257004[161] = 0;
   out_548560934011257004[162] = 0;
   out_548560934011257004[163] = 0;
   out_548560934011257004[164] = 0;
   out_548560934011257004[165] = 0;
   out_548560934011257004[166] = 0;
   out_548560934011257004[167] = 0;
   out_548560934011257004[168] = 0;
   out_548560934011257004[169] = 0;
   out_548560934011257004[170] = 0;
   out_548560934011257004[171] = 1;
   out_548560934011257004[172] = 0;
   out_548560934011257004[173] = 0;
   out_548560934011257004[174] = 0;
   out_548560934011257004[175] = 0;
   out_548560934011257004[176] = 0;
   out_548560934011257004[177] = 0;
   out_548560934011257004[178] = 0;
   out_548560934011257004[179] = 0;
   out_548560934011257004[180] = 0;
   out_548560934011257004[181] = 0;
   out_548560934011257004[182] = 0;
   out_548560934011257004[183] = 0;
   out_548560934011257004[184] = 0;
   out_548560934011257004[185] = 0;
   out_548560934011257004[186] = 0;
   out_548560934011257004[187] = 0;
   out_548560934011257004[188] = 0;
   out_548560934011257004[189] = 0;
   out_548560934011257004[190] = 1;
   out_548560934011257004[191] = 0;
   out_548560934011257004[192] = 0;
   out_548560934011257004[193] = 0;
   out_548560934011257004[194] = 0;
   out_548560934011257004[195] = 0;
   out_548560934011257004[196] = 0;
   out_548560934011257004[197] = 0;
   out_548560934011257004[198] = 0;
   out_548560934011257004[199] = 0;
   out_548560934011257004[200] = 0;
   out_548560934011257004[201] = 0;
   out_548560934011257004[202] = 0;
   out_548560934011257004[203] = 0;
   out_548560934011257004[204] = 0;
   out_548560934011257004[205] = 0;
   out_548560934011257004[206] = 0;
   out_548560934011257004[207] = 0;
   out_548560934011257004[208] = 0;
   out_548560934011257004[209] = 1;
   out_548560934011257004[210] = 0;
   out_548560934011257004[211] = 0;
   out_548560934011257004[212] = 0;
   out_548560934011257004[213] = 0;
   out_548560934011257004[214] = 0;
   out_548560934011257004[215] = 0;
   out_548560934011257004[216] = 0;
   out_548560934011257004[217] = 0;
   out_548560934011257004[218] = 0;
   out_548560934011257004[219] = 0;
   out_548560934011257004[220] = 0;
   out_548560934011257004[221] = 0;
   out_548560934011257004[222] = 0;
   out_548560934011257004[223] = 0;
   out_548560934011257004[224] = 0;
   out_548560934011257004[225] = 0;
   out_548560934011257004[226] = 0;
   out_548560934011257004[227] = 0;
   out_548560934011257004[228] = 1;
   out_548560934011257004[229] = 0;
   out_548560934011257004[230] = 0;
   out_548560934011257004[231] = 0;
   out_548560934011257004[232] = 0;
   out_548560934011257004[233] = 0;
   out_548560934011257004[234] = 0;
   out_548560934011257004[235] = 0;
   out_548560934011257004[236] = 0;
   out_548560934011257004[237] = 0;
   out_548560934011257004[238] = 0;
   out_548560934011257004[239] = 0;
   out_548560934011257004[240] = 0;
   out_548560934011257004[241] = 0;
   out_548560934011257004[242] = 0;
   out_548560934011257004[243] = 0;
   out_548560934011257004[244] = 0;
   out_548560934011257004[245] = 0;
   out_548560934011257004[246] = 0;
   out_548560934011257004[247] = 1;
   out_548560934011257004[248] = 0;
   out_548560934011257004[249] = 0;
   out_548560934011257004[250] = 0;
   out_548560934011257004[251] = 0;
   out_548560934011257004[252] = 0;
   out_548560934011257004[253] = 0;
   out_548560934011257004[254] = 0;
   out_548560934011257004[255] = 0;
   out_548560934011257004[256] = 0;
   out_548560934011257004[257] = 0;
   out_548560934011257004[258] = 0;
   out_548560934011257004[259] = 0;
   out_548560934011257004[260] = 0;
   out_548560934011257004[261] = 0;
   out_548560934011257004[262] = 0;
   out_548560934011257004[263] = 0;
   out_548560934011257004[264] = 0;
   out_548560934011257004[265] = 0;
   out_548560934011257004[266] = 1;
   out_548560934011257004[267] = 0;
   out_548560934011257004[268] = 0;
   out_548560934011257004[269] = 0;
   out_548560934011257004[270] = 0;
   out_548560934011257004[271] = 0;
   out_548560934011257004[272] = 0;
   out_548560934011257004[273] = 0;
   out_548560934011257004[274] = 0;
   out_548560934011257004[275] = 0;
   out_548560934011257004[276] = 0;
   out_548560934011257004[277] = 0;
   out_548560934011257004[278] = 0;
   out_548560934011257004[279] = 0;
   out_548560934011257004[280] = 0;
   out_548560934011257004[281] = 0;
   out_548560934011257004[282] = 0;
   out_548560934011257004[283] = 0;
   out_548560934011257004[284] = 0;
   out_548560934011257004[285] = 1;
   out_548560934011257004[286] = 0;
   out_548560934011257004[287] = 0;
   out_548560934011257004[288] = 0;
   out_548560934011257004[289] = 0;
   out_548560934011257004[290] = 0;
   out_548560934011257004[291] = 0;
   out_548560934011257004[292] = 0;
   out_548560934011257004[293] = 0;
   out_548560934011257004[294] = 0;
   out_548560934011257004[295] = 0;
   out_548560934011257004[296] = 0;
   out_548560934011257004[297] = 0;
   out_548560934011257004[298] = 0;
   out_548560934011257004[299] = 0;
   out_548560934011257004[300] = 0;
   out_548560934011257004[301] = 0;
   out_548560934011257004[302] = 0;
   out_548560934011257004[303] = 0;
   out_548560934011257004[304] = 1;
   out_548560934011257004[305] = 0;
   out_548560934011257004[306] = 0;
   out_548560934011257004[307] = 0;
   out_548560934011257004[308] = 0;
   out_548560934011257004[309] = 0;
   out_548560934011257004[310] = 0;
   out_548560934011257004[311] = 0;
   out_548560934011257004[312] = 0;
   out_548560934011257004[313] = 0;
   out_548560934011257004[314] = 0;
   out_548560934011257004[315] = 0;
   out_548560934011257004[316] = 0;
   out_548560934011257004[317] = 0;
   out_548560934011257004[318] = 0;
   out_548560934011257004[319] = 0;
   out_548560934011257004[320] = 0;
   out_548560934011257004[321] = 0;
   out_548560934011257004[322] = 0;
   out_548560934011257004[323] = 1;
}
void h_4(double *state, double *unused, double *out_6958379897591079591) {
   out_6958379897591079591[0] = state[6] + state[9];
   out_6958379897591079591[1] = state[7] + state[10];
   out_6958379897591079591[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_8241463700949695206) {
   out_8241463700949695206[0] = 0;
   out_8241463700949695206[1] = 0;
   out_8241463700949695206[2] = 0;
   out_8241463700949695206[3] = 0;
   out_8241463700949695206[4] = 0;
   out_8241463700949695206[5] = 0;
   out_8241463700949695206[6] = 1;
   out_8241463700949695206[7] = 0;
   out_8241463700949695206[8] = 0;
   out_8241463700949695206[9] = 1;
   out_8241463700949695206[10] = 0;
   out_8241463700949695206[11] = 0;
   out_8241463700949695206[12] = 0;
   out_8241463700949695206[13] = 0;
   out_8241463700949695206[14] = 0;
   out_8241463700949695206[15] = 0;
   out_8241463700949695206[16] = 0;
   out_8241463700949695206[17] = 0;
   out_8241463700949695206[18] = 0;
   out_8241463700949695206[19] = 0;
   out_8241463700949695206[20] = 0;
   out_8241463700949695206[21] = 0;
   out_8241463700949695206[22] = 0;
   out_8241463700949695206[23] = 0;
   out_8241463700949695206[24] = 0;
   out_8241463700949695206[25] = 1;
   out_8241463700949695206[26] = 0;
   out_8241463700949695206[27] = 0;
   out_8241463700949695206[28] = 1;
   out_8241463700949695206[29] = 0;
   out_8241463700949695206[30] = 0;
   out_8241463700949695206[31] = 0;
   out_8241463700949695206[32] = 0;
   out_8241463700949695206[33] = 0;
   out_8241463700949695206[34] = 0;
   out_8241463700949695206[35] = 0;
   out_8241463700949695206[36] = 0;
   out_8241463700949695206[37] = 0;
   out_8241463700949695206[38] = 0;
   out_8241463700949695206[39] = 0;
   out_8241463700949695206[40] = 0;
   out_8241463700949695206[41] = 0;
   out_8241463700949695206[42] = 0;
   out_8241463700949695206[43] = 0;
   out_8241463700949695206[44] = 1;
   out_8241463700949695206[45] = 0;
   out_8241463700949695206[46] = 0;
   out_8241463700949695206[47] = 1;
   out_8241463700949695206[48] = 0;
   out_8241463700949695206[49] = 0;
   out_8241463700949695206[50] = 0;
   out_8241463700949695206[51] = 0;
   out_8241463700949695206[52] = 0;
   out_8241463700949695206[53] = 0;
}
void h_10(double *state, double *unused, double *out_1729099690168305282) {
   out_1729099690168305282[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_1729099690168305282[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_1729099690168305282[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_8703653728891909942) {
   out_8703653728891909942[0] = 0;
   out_8703653728891909942[1] = 9.8100000000000005*cos(state[1]);
   out_8703653728891909942[2] = 0;
   out_8703653728891909942[3] = 0;
   out_8703653728891909942[4] = -state[8];
   out_8703653728891909942[5] = state[7];
   out_8703653728891909942[6] = 0;
   out_8703653728891909942[7] = state[5];
   out_8703653728891909942[8] = -state[4];
   out_8703653728891909942[9] = 0;
   out_8703653728891909942[10] = 0;
   out_8703653728891909942[11] = 0;
   out_8703653728891909942[12] = 1;
   out_8703653728891909942[13] = 0;
   out_8703653728891909942[14] = 0;
   out_8703653728891909942[15] = 1;
   out_8703653728891909942[16] = 0;
   out_8703653728891909942[17] = 0;
   out_8703653728891909942[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_8703653728891909942[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_8703653728891909942[20] = 0;
   out_8703653728891909942[21] = state[8];
   out_8703653728891909942[22] = 0;
   out_8703653728891909942[23] = -state[6];
   out_8703653728891909942[24] = -state[5];
   out_8703653728891909942[25] = 0;
   out_8703653728891909942[26] = state[3];
   out_8703653728891909942[27] = 0;
   out_8703653728891909942[28] = 0;
   out_8703653728891909942[29] = 0;
   out_8703653728891909942[30] = 0;
   out_8703653728891909942[31] = 1;
   out_8703653728891909942[32] = 0;
   out_8703653728891909942[33] = 0;
   out_8703653728891909942[34] = 1;
   out_8703653728891909942[35] = 0;
   out_8703653728891909942[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_8703653728891909942[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_8703653728891909942[38] = 0;
   out_8703653728891909942[39] = -state[7];
   out_8703653728891909942[40] = state[6];
   out_8703653728891909942[41] = 0;
   out_8703653728891909942[42] = state[4];
   out_8703653728891909942[43] = -state[3];
   out_8703653728891909942[44] = 0;
   out_8703653728891909942[45] = 0;
   out_8703653728891909942[46] = 0;
   out_8703653728891909942[47] = 0;
   out_8703653728891909942[48] = 0;
   out_8703653728891909942[49] = 0;
   out_8703653728891909942[50] = 1;
   out_8703653728891909942[51] = 0;
   out_8703653728891909942[52] = 0;
   out_8703653728891909942[53] = 1;
}
void h_13(double *state, double *unused, double *out_1797642900140291675) {
   out_1797642900140291675[0] = state[3];
   out_1797642900140291675[1] = state[4];
   out_1797642900140291675[2] = state[5];
}
void H_13(double *state, double *unused, double *out_5029189875617362405) {
   out_5029189875617362405[0] = 0;
   out_5029189875617362405[1] = 0;
   out_5029189875617362405[2] = 0;
   out_5029189875617362405[3] = 1;
   out_5029189875617362405[4] = 0;
   out_5029189875617362405[5] = 0;
   out_5029189875617362405[6] = 0;
   out_5029189875617362405[7] = 0;
   out_5029189875617362405[8] = 0;
   out_5029189875617362405[9] = 0;
   out_5029189875617362405[10] = 0;
   out_5029189875617362405[11] = 0;
   out_5029189875617362405[12] = 0;
   out_5029189875617362405[13] = 0;
   out_5029189875617362405[14] = 0;
   out_5029189875617362405[15] = 0;
   out_5029189875617362405[16] = 0;
   out_5029189875617362405[17] = 0;
   out_5029189875617362405[18] = 0;
   out_5029189875617362405[19] = 0;
   out_5029189875617362405[20] = 0;
   out_5029189875617362405[21] = 0;
   out_5029189875617362405[22] = 1;
   out_5029189875617362405[23] = 0;
   out_5029189875617362405[24] = 0;
   out_5029189875617362405[25] = 0;
   out_5029189875617362405[26] = 0;
   out_5029189875617362405[27] = 0;
   out_5029189875617362405[28] = 0;
   out_5029189875617362405[29] = 0;
   out_5029189875617362405[30] = 0;
   out_5029189875617362405[31] = 0;
   out_5029189875617362405[32] = 0;
   out_5029189875617362405[33] = 0;
   out_5029189875617362405[34] = 0;
   out_5029189875617362405[35] = 0;
   out_5029189875617362405[36] = 0;
   out_5029189875617362405[37] = 0;
   out_5029189875617362405[38] = 0;
   out_5029189875617362405[39] = 0;
   out_5029189875617362405[40] = 0;
   out_5029189875617362405[41] = 1;
   out_5029189875617362405[42] = 0;
   out_5029189875617362405[43] = 0;
   out_5029189875617362405[44] = 0;
   out_5029189875617362405[45] = 0;
   out_5029189875617362405[46] = 0;
   out_5029189875617362405[47] = 0;
   out_5029189875617362405[48] = 0;
   out_5029189875617362405[49] = 0;
   out_5029189875617362405[50] = 0;
   out_5029189875617362405[51] = 0;
   out_5029189875617362405[52] = 0;
   out_5029189875617362405[53] = 0;
}
void h_14(double *state, double *unused, double *out_4924798979149113609) {
   out_4924798979149113609[0] = state[6];
   out_4924798979149113609[1] = state[7];
   out_4924798979149113609[2] = state[8];
}
void H_14(double *state, double *unused, double *out_7122491940464484114) {
   out_7122491940464484114[0] = 0;
   out_7122491940464484114[1] = 0;
   out_7122491940464484114[2] = 0;
   out_7122491940464484114[3] = 0;
   out_7122491940464484114[4] = 0;
   out_7122491940464484114[5] = 0;
   out_7122491940464484114[6] = 1;
   out_7122491940464484114[7] = 0;
   out_7122491940464484114[8] = 0;
   out_7122491940464484114[9] = 0;
   out_7122491940464484114[10] = 0;
   out_7122491940464484114[11] = 0;
   out_7122491940464484114[12] = 0;
   out_7122491940464484114[13] = 0;
   out_7122491940464484114[14] = 0;
   out_7122491940464484114[15] = 0;
   out_7122491940464484114[16] = 0;
   out_7122491940464484114[17] = 0;
   out_7122491940464484114[18] = 0;
   out_7122491940464484114[19] = 0;
   out_7122491940464484114[20] = 0;
   out_7122491940464484114[21] = 0;
   out_7122491940464484114[22] = 0;
   out_7122491940464484114[23] = 0;
   out_7122491940464484114[24] = 0;
   out_7122491940464484114[25] = 1;
   out_7122491940464484114[26] = 0;
   out_7122491940464484114[27] = 0;
   out_7122491940464484114[28] = 0;
   out_7122491940464484114[29] = 0;
   out_7122491940464484114[30] = 0;
   out_7122491940464484114[31] = 0;
   out_7122491940464484114[32] = 0;
   out_7122491940464484114[33] = 0;
   out_7122491940464484114[34] = 0;
   out_7122491940464484114[35] = 0;
   out_7122491940464484114[36] = 0;
   out_7122491940464484114[37] = 0;
   out_7122491940464484114[38] = 0;
   out_7122491940464484114[39] = 0;
   out_7122491940464484114[40] = 0;
   out_7122491940464484114[41] = 0;
   out_7122491940464484114[42] = 0;
   out_7122491940464484114[43] = 0;
   out_7122491940464484114[44] = 1;
   out_7122491940464484114[45] = 0;
   out_7122491940464484114[46] = 0;
   out_7122491940464484114[47] = 0;
   out_7122491940464484114[48] = 0;
   out_7122491940464484114[49] = 0;
   out_7122491940464484114[50] = 0;
   out_7122491940464484114[51] = 0;
   out_7122491940464484114[52] = 0;
   out_7122491940464484114[53] = 0;
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
void pose_err_fun(double *nom_x, double *delta_x, double *out_377710204961129279) {
  err_fun(nom_x, delta_x, out_377710204961129279);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_2728279097657860545) {
  inv_err_fun(nom_x, true_x, out_2728279097657860545);
}
void pose_H_mod_fun(double *state, double *out_8995624703004407813) {
  H_mod_fun(state, out_8995624703004407813);
}
void pose_f_fun(double *state, double dt, double *out_4645218274869152611) {
  f_fun(state,  dt, out_4645218274869152611);
}
void pose_F_fun(double *state, double dt, double *out_548560934011257004) {
  F_fun(state,  dt, out_548560934011257004);
}
void pose_h_4(double *state, double *unused, double *out_6958379897591079591) {
  h_4(state, unused, out_6958379897591079591);
}
void pose_H_4(double *state, double *unused, double *out_8241463700949695206) {
  H_4(state, unused, out_8241463700949695206);
}
void pose_h_10(double *state, double *unused, double *out_1729099690168305282) {
  h_10(state, unused, out_1729099690168305282);
}
void pose_H_10(double *state, double *unused, double *out_8703653728891909942) {
  H_10(state, unused, out_8703653728891909942);
}
void pose_h_13(double *state, double *unused, double *out_1797642900140291675) {
  h_13(state, unused, out_1797642900140291675);
}
void pose_H_13(double *state, double *unused, double *out_5029189875617362405) {
  H_13(state, unused, out_5029189875617362405);
}
void pose_h_14(double *state, double *unused, double *out_4924798979149113609) {
  h_14(state, unused, out_4924798979149113609);
}
void pose_H_14(double *state, double *unused, double *out_7122491940464484114) {
  H_14(state, unused, out_7122491940464484114);
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
