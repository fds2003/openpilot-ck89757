#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_7162185252314982128);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_7960070363622900651);
void car_H_mod_fun(double *state, double *out_262597332355746347);
void car_f_fun(double *state, double dt, double *out_3892164267283524868);
void car_F_fun(double *state, double dt, double *out_2110431214458564445);
void car_h_25(double *state, double *unused, double *out_3615703142255965907);
void car_H_25(double *state, double *unused, double *out_3260383317633745330);
void car_h_24(double *state, double *unused, double *out_4389041207541638847);
void car_H_24(double *state, double *unused, double *out_6818308916436068466);
void car_h_30(double *state, double *unused, double *out_8060205705103234773);
void car_H_30(double *state, double *unused, double *out_8269670414584189531);
void car_h_26(double *state, double *unused, double *out_3058532437442389128);
void car_H_26(double *state, double *unused, double *out_481120001240310894);
void car_h_27(double *state, double *unused, double *out_782248939025663105);
void car_H_27(double *state, double *unused, double *out_8002310347324937174);
void car_h_29(double *state, double *unused, double *out_4643932415454164757);
void car_H_29(double *state, double *unused, double *out_6288947620455386141);
void car_h_28(double *state, double *unused, double *out_161260913875999330);
void car_H_28(double *state, double *unused, double *out_1206548603385855567);
void car_h_31(double *state, double *unused, double *out_2768792936006299373);
void car_H_31(double *state, double *unused, double *out_3291029279510705758);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}