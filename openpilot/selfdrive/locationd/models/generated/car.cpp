#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_7162185252314982128) {
   out_7162185252314982128[0] = delta_x[0] + nom_x[0];
   out_7162185252314982128[1] = delta_x[1] + nom_x[1];
   out_7162185252314982128[2] = delta_x[2] + nom_x[2];
   out_7162185252314982128[3] = delta_x[3] + nom_x[3];
   out_7162185252314982128[4] = delta_x[4] + nom_x[4];
   out_7162185252314982128[5] = delta_x[5] + nom_x[5];
   out_7162185252314982128[6] = delta_x[6] + nom_x[6];
   out_7162185252314982128[7] = delta_x[7] + nom_x[7];
   out_7162185252314982128[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_7960070363622900651) {
   out_7960070363622900651[0] = -nom_x[0] + true_x[0];
   out_7960070363622900651[1] = -nom_x[1] + true_x[1];
   out_7960070363622900651[2] = -nom_x[2] + true_x[2];
   out_7960070363622900651[3] = -nom_x[3] + true_x[3];
   out_7960070363622900651[4] = -nom_x[4] + true_x[4];
   out_7960070363622900651[5] = -nom_x[5] + true_x[5];
   out_7960070363622900651[6] = -nom_x[6] + true_x[6];
   out_7960070363622900651[7] = -nom_x[7] + true_x[7];
   out_7960070363622900651[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_262597332355746347) {
   out_262597332355746347[0] = 1.0;
   out_262597332355746347[1] = 0.0;
   out_262597332355746347[2] = 0.0;
   out_262597332355746347[3] = 0.0;
   out_262597332355746347[4] = 0.0;
   out_262597332355746347[5] = 0.0;
   out_262597332355746347[6] = 0.0;
   out_262597332355746347[7] = 0.0;
   out_262597332355746347[8] = 0.0;
   out_262597332355746347[9] = 0.0;
   out_262597332355746347[10] = 1.0;
   out_262597332355746347[11] = 0.0;
   out_262597332355746347[12] = 0.0;
   out_262597332355746347[13] = 0.0;
   out_262597332355746347[14] = 0.0;
   out_262597332355746347[15] = 0.0;
   out_262597332355746347[16] = 0.0;
   out_262597332355746347[17] = 0.0;
   out_262597332355746347[18] = 0.0;
   out_262597332355746347[19] = 0.0;
   out_262597332355746347[20] = 1.0;
   out_262597332355746347[21] = 0.0;
   out_262597332355746347[22] = 0.0;
   out_262597332355746347[23] = 0.0;
   out_262597332355746347[24] = 0.0;
   out_262597332355746347[25] = 0.0;
   out_262597332355746347[26] = 0.0;
   out_262597332355746347[27] = 0.0;
   out_262597332355746347[28] = 0.0;
   out_262597332355746347[29] = 0.0;
   out_262597332355746347[30] = 1.0;
   out_262597332355746347[31] = 0.0;
   out_262597332355746347[32] = 0.0;
   out_262597332355746347[33] = 0.0;
   out_262597332355746347[34] = 0.0;
   out_262597332355746347[35] = 0.0;
   out_262597332355746347[36] = 0.0;
   out_262597332355746347[37] = 0.0;
   out_262597332355746347[38] = 0.0;
   out_262597332355746347[39] = 0.0;
   out_262597332355746347[40] = 1.0;
   out_262597332355746347[41] = 0.0;
   out_262597332355746347[42] = 0.0;
   out_262597332355746347[43] = 0.0;
   out_262597332355746347[44] = 0.0;
   out_262597332355746347[45] = 0.0;
   out_262597332355746347[46] = 0.0;
   out_262597332355746347[47] = 0.0;
   out_262597332355746347[48] = 0.0;
   out_262597332355746347[49] = 0.0;
   out_262597332355746347[50] = 1.0;
   out_262597332355746347[51] = 0.0;
   out_262597332355746347[52] = 0.0;
   out_262597332355746347[53] = 0.0;
   out_262597332355746347[54] = 0.0;
   out_262597332355746347[55] = 0.0;
   out_262597332355746347[56] = 0.0;
   out_262597332355746347[57] = 0.0;
   out_262597332355746347[58] = 0.0;
   out_262597332355746347[59] = 0.0;
   out_262597332355746347[60] = 1.0;
   out_262597332355746347[61] = 0.0;
   out_262597332355746347[62] = 0.0;
   out_262597332355746347[63] = 0.0;
   out_262597332355746347[64] = 0.0;
   out_262597332355746347[65] = 0.0;
   out_262597332355746347[66] = 0.0;
   out_262597332355746347[67] = 0.0;
   out_262597332355746347[68] = 0.0;
   out_262597332355746347[69] = 0.0;
   out_262597332355746347[70] = 1.0;
   out_262597332355746347[71] = 0.0;
   out_262597332355746347[72] = 0.0;
   out_262597332355746347[73] = 0.0;
   out_262597332355746347[74] = 0.0;
   out_262597332355746347[75] = 0.0;
   out_262597332355746347[76] = 0.0;
   out_262597332355746347[77] = 0.0;
   out_262597332355746347[78] = 0.0;
   out_262597332355746347[79] = 0.0;
   out_262597332355746347[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_3892164267283524868) {
   out_3892164267283524868[0] = state[0];
   out_3892164267283524868[1] = state[1];
   out_3892164267283524868[2] = state[2];
   out_3892164267283524868[3] = state[3];
   out_3892164267283524868[4] = state[4];
   out_3892164267283524868[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_3892164267283524868[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_3892164267283524868[7] = state[7];
   out_3892164267283524868[8] = state[8];
}
void F_fun(double *state, double dt, double *out_2110431214458564445) {
   out_2110431214458564445[0] = 1;
   out_2110431214458564445[1] = 0;
   out_2110431214458564445[2] = 0;
   out_2110431214458564445[3] = 0;
   out_2110431214458564445[4] = 0;
   out_2110431214458564445[5] = 0;
   out_2110431214458564445[6] = 0;
   out_2110431214458564445[7] = 0;
   out_2110431214458564445[8] = 0;
   out_2110431214458564445[9] = 0;
   out_2110431214458564445[10] = 1;
   out_2110431214458564445[11] = 0;
   out_2110431214458564445[12] = 0;
   out_2110431214458564445[13] = 0;
   out_2110431214458564445[14] = 0;
   out_2110431214458564445[15] = 0;
   out_2110431214458564445[16] = 0;
   out_2110431214458564445[17] = 0;
   out_2110431214458564445[18] = 0;
   out_2110431214458564445[19] = 0;
   out_2110431214458564445[20] = 1;
   out_2110431214458564445[21] = 0;
   out_2110431214458564445[22] = 0;
   out_2110431214458564445[23] = 0;
   out_2110431214458564445[24] = 0;
   out_2110431214458564445[25] = 0;
   out_2110431214458564445[26] = 0;
   out_2110431214458564445[27] = 0;
   out_2110431214458564445[28] = 0;
   out_2110431214458564445[29] = 0;
   out_2110431214458564445[30] = 1;
   out_2110431214458564445[31] = 0;
   out_2110431214458564445[32] = 0;
   out_2110431214458564445[33] = 0;
   out_2110431214458564445[34] = 0;
   out_2110431214458564445[35] = 0;
   out_2110431214458564445[36] = 0;
   out_2110431214458564445[37] = 0;
   out_2110431214458564445[38] = 0;
   out_2110431214458564445[39] = 0;
   out_2110431214458564445[40] = 1;
   out_2110431214458564445[41] = 0;
   out_2110431214458564445[42] = 0;
   out_2110431214458564445[43] = 0;
   out_2110431214458564445[44] = 0;
   out_2110431214458564445[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_2110431214458564445[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_2110431214458564445[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_2110431214458564445[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_2110431214458564445[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_2110431214458564445[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_2110431214458564445[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_2110431214458564445[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_2110431214458564445[53] = -9.8100000000000005*dt;
   out_2110431214458564445[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_2110431214458564445[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_2110431214458564445[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_2110431214458564445[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_2110431214458564445[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_2110431214458564445[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_2110431214458564445[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_2110431214458564445[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_2110431214458564445[62] = 0;
   out_2110431214458564445[63] = 0;
   out_2110431214458564445[64] = 0;
   out_2110431214458564445[65] = 0;
   out_2110431214458564445[66] = 0;
   out_2110431214458564445[67] = 0;
   out_2110431214458564445[68] = 0;
   out_2110431214458564445[69] = 0;
   out_2110431214458564445[70] = 1;
   out_2110431214458564445[71] = 0;
   out_2110431214458564445[72] = 0;
   out_2110431214458564445[73] = 0;
   out_2110431214458564445[74] = 0;
   out_2110431214458564445[75] = 0;
   out_2110431214458564445[76] = 0;
   out_2110431214458564445[77] = 0;
   out_2110431214458564445[78] = 0;
   out_2110431214458564445[79] = 0;
   out_2110431214458564445[80] = 1;
}
void h_25(double *state, double *unused, double *out_3615703142255965907) {
   out_3615703142255965907[0] = state[6];
}
void H_25(double *state, double *unused, double *out_3260383317633745330) {
   out_3260383317633745330[0] = 0;
   out_3260383317633745330[1] = 0;
   out_3260383317633745330[2] = 0;
   out_3260383317633745330[3] = 0;
   out_3260383317633745330[4] = 0;
   out_3260383317633745330[5] = 0;
   out_3260383317633745330[6] = 1;
   out_3260383317633745330[7] = 0;
   out_3260383317633745330[8] = 0;
}
void h_24(double *state, double *unused, double *out_4389041207541638847) {
   out_4389041207541638847[0] = state[4];
   out_4389041207541638847[1] = state[5];
}
void H_24(double *state, double *unused, double *out_6818308916436068466) {
   out_6818308916436068466[0] = 0;
   out_6818308916436068466[1] = 0;
   out_6818308916436068466[2] = 0;
   out_6818308916436068466[3] = 0;
   out_6818308916436068466[4] = 1;
   out_6818308916436068466[5] = 0;
   out_6818308916436068466[6] = 0;
   out_6818308916436068466[7] = 0;
   out_6818308916436068466[8] = 0;
   out_6818308916436068466[9] = 0;
   out_6818308916436068466[10] = 0;
   out_6818308916436068466[11] = 0;
   out_6818308916436068466[12] = 0;
   out_6818308916436068466[13] = 0;
   out_6818308916436068466[14] = 1;
   out_6818308916436068466[15] = 0;
   out_6818308916436068466[16] = 0;
   out_6818308916436068466[17] = 0;
}
void h_30(double *state, double *unused, double *out_8060205705103234773) {
   out_8060205705103234773[0] = state[4];
}
void H_30(double *state, double *unused, double *out_8269670414584189531) {
   out_8269670414584189531[0] = 0;
   out_8269670414584189531[1] = 0;
   out_8269670414584189531[2] = 0;
   out_8269670414584189531[3] = 0;
   out_8269670414584189531[4] = 1;
   out_8269670414584189531[5] = 0;
   out_8269670414584189531[6] = 0;
   out_8269670414584189531[7] = 0;
   out_8269670414584189531[8] = 0;
}
void h_26(double *state, double *unused, double *out_3058532437442389128) {
   out_3058532437442389128[0] = state[7];
}
void H_26(double *state, double *unused, double *out_481120001240310894) {
   out_481120001240310894[0] = 0;
   out_481120001240310894[1] = 0;
   out_481120001240310894[2] = 0;
   out_481120001240310894[3] = 0;
   out_481120001240310894[4] = 0;
   out_481120001240310894[5] = 0;
   out_481120001240310894[6] = 0;
   out_481120001240310894[7] = 1;
   out_481120001240310894[8] = 0;
}
void h_27(double *state, double *unused, double *out_782248939025663105) {
   out_782248939025663105[0] = state[3];
}
void H_27(double *state, double *unused, double *out_8002310347324937174) {
   out_8002310347324937174[0] = 0;
   out_8002310347324937174[1] = 0;
   out_8002310347324937174[2] = 0;
   out_8002310347324937174[3] = 1;
   out_8002310347324937174[4] = 0;
   out_8002310347324937174[5] = 0;
   out_8002310347324937174[6] = 0;
   out_8002310347324937174[7] = 0;
   out_8002310347324937174[8] = 0;
}
void h_29(double *state, double *unused, double *out_4643932415454164757) {
   out_4643932415454164757[0] = state[1];
}
void H_29(double *state, double *unused, double *out_6288947620455386141) {
   out_6288947620455386141[0] = 0;
   out_6288947620455386141[1] = 1;
   out_6288947620455386141[2] = 0;
   out_6288947620455386141[3] = 0;
   out_6288947620455386141[4] = 0;
   out_6288947620455386141[5] = 0;
   out_6288947620455386141[6] = 0;
   out_6288947620455386141[7] = 0;
   out_6288947620455386141[8] = 0;
}
void h_28(double *state, double *unused, double *out_161260913875999330) {
   out_161260913875999330[0] = state[0];
}
void H_28(double *state, double *unused, double *out_1206548603385855567) {
   out_1206548603385855567[0] = 1;
   out_1206548603385855567[1] = 0;
   out_1206548603385855567[2] = 0;
   out_1206548603385855567[3] = 0;
   out_1206548603385855567[4] = 0;
   out_1206548603385855567[5] = 0;
   out_1206548603385855567[6] = 0;
   out_1206548603385855567[7] = 0;
   out_1206548603385855567[8] = 0;
}
void h_31(double *state, double *unused, double *out_2768792936006299373) {
   out_2768792936006299373[0] = state[8];
}
void H_31(double *state, double *unused, double *out_3291029279510705758) {
   out_3291029279510705758[0] = 0;
   out_3291029279510705758[1] = 0;
   out_3291029279510705758[2] = 0;
   out_3291029279510705758[3] = 0;
   out_3291029279510705758[4] = 0;
   out_3291029279510705758[5] = 0;
   out_3291029279510705758[6] = 0;
   out_3291029279510705758[7] = 0;
   out_3291029279510705758[8] = 1;
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

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_7162185252314982128) {
  err_fun(nom_x, delta_x, out_7162185252314982128);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_7960070363622900651) {
  inv_err_fun(nom_x, true_x, out_7960070363622900651);
}
void car_H_mod_fun(double *state, double *out_262597332355746347) {
  H_mod_fun(state, out_262597332355746347);
}
void car_f_fun(double *state, double dt, double *out_3892164267283524868) {
  f_fun(state,  dt, out_3892164267283524868);
}
void car_F_fun(double *state, double dt, double *out_2110431214458564445) {
  F_fun(state,  dt, out_2110431214458564445);
}
void car_h_25(double *state, double *unused, double *out_3615703142255965907) {
  h_25(state, unused, out_3615703142255965907);
}
void car_H_25(double *state, double *unused, double *out_3260383317633745330) {
  H_25(state, unused, out_3260383317633745330);
}
void car_h_24(double *state, double *unused, double *out_4389041207541638847) {
  h_24(state, unused, out_4389041207541638847);
}
void car_H_24(double *state, double *unused, double *out_6818308916436068466) {
  H_24(state, unused, out_6818308916436068466);
}
void car_h_30(double *state, double *unused, double *out_8060205705103234773) {
  h_30(state, unused, out_8060205705103234773);
}
void car_H_30(double *state, double *unused, double *out_8269670414584189531) {
  H_30(state, unused, out_8269670414584189531);
}
void car_h_26(double *state, double *unused, double *out_3058532437442389128) {
  h_26(state, unused, out_3058532437442389128);
}
void car_H_26(double *state, double *unused, double *out_481120001240310894) {
  H_26(state, unused, out_481120001240310894);
}
void car_h_27(double *state, double *unused, double *out_782248939025663105) {
  h_27(state, unused, out_782248939025663105);
}
void car_H_27(double *state, double *unused, double *out_8002310347324937174) {
  H_27(state, unused, out_8002310347324937174);
}
void car_h_29(double *state, double *unused, double *out_4643932415454164757) {
  h_29(state, unused, out_4643932415454164757);
}
void car_H_29(double *state, double *unused, double *out_6288947620455386141) {
  H_29(state, unused, out_6288947620455386141);
}
void car_h_28(double *state, double *unused, double *out_161260913875999330) {
  h_28(state, unused, out_161260913875999330);
}
void car_H_28(double *state, double *unused, double *out_1206548603385855567) {
  H_28(state, unused, out_1206548603385855567);
}
void car_h_31(double *state, double *unused, double *out_2768792936006299373) {
  h_31(state, unused, out_2768792936006299373);
}
void car_H_31(double *state, double *unused, double *out_3291029279510705758) {
  H_31(state, unused, out_3291029279510705758);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
