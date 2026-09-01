#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_377710204961129279);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_2728279097657860545);
void pose_H_mod_fun(double *state, double *out_8995624703004407813);
void pose_f_fun(double *state, double dt, double *out_4645218274869152611);
void pose_F_fun(double *state, double dt, double *out_548560934011257004);
void pose_h_4(double *state, double *unused, double *out_6958379897591079591);
void pose_H_4(double *state, double *unused, double *out_8241463700949695206);
void pose_h_10(double *state, double *unused, double *out_1729099690168305282);
void pose_H_10(double *state, double *unused, double *out_8703653728891909942);
void pose_h_13(double *state, double *unused, double *out_1797642900140291675);
void pose_H_13(double *state, double *unused, double *out_5029189875617362405);
void pose_h_14(double *state, double *unused, double *out_4924798979149113609);
void pose_H_14(double *state, double *unused, double *out_7122491940464484114);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}