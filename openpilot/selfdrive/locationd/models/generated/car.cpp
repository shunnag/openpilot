#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

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
void err_fun(double *nom_x, double *delta_x, double *out_8135642088081730923) {
   out_8135642088081730923[0] = delta_x[0] + nom_x[0];
   out_8135642088081730923[1] = delta_x[1] + nom_x[1];
   out_8135642088081730923[2] = delta_x[2] + nom_x[2];
   out_8135642088081730923[3] = delta_x[3] + nom_x[3];
   out_8135642088081730923[4] = delta_x[4] + nom_x[4];
   out_8135642088081730923[5] = delta_x[5] + nom_x[5];
   out_8135642088081730923[6] = delta_x[6] + nom_x[6];
   out_8135642088081730923[7] = delta_x[7] + nom_x[7];
   out_8135642088081730923[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_8016091243247573615) {
   out_8016091243247573615[0] = -nom_x[0] + true_x[0];
   out_8016091243247573615[1] = -nom_x[1] + true_x[1];
   out_8016091243247573615[2] = -nom_x[2] + true_x[2];
   out_8016091243247573615[3] = -nom_x[3] + true_x[3];
   out_8016091243247573615[4] = -nom_x[4] + true_x[4];
   out_8016091243247573615[5] = -nom_x[5] + true_x[5];
   out_8016091243247573615[6] = -nom_x[6] + true_x[6];
   out_8016091243247573615[7] = -nom_x[7] + true_x[7];
   out_8016091243247573615[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_2256966125820776418) {
   out_2256966125820776418[0] = 1.0;
   out_2256966125820776418[1] = 0.0;
   out_2256966125820776418[2] = 0.0;
   out_2256966125820776418[3] = 0.0;
   out_2256966125820776418[4] = 0.0;
   out_2256966125820776418[5] = 0.0;
   out_2256966125820776418[6] = 0.0;
   out_2256966125820776418[7] = 0.0;
   out_2256966125820776418[8] = 0.0;
   out_2256966125820776418[9] = 0.0;
   out_2256966125820776418[10] = 1.0;
   out_2256966125820776418[11] = 0.0;
   out_2256966125820776418[12] = 0.0;
   out_2256966125820776418[13] = 0.0;
   out_2256966125820776418[14] = 0.0;
   out_2256966125820776418[15] = 0.0;
   out_2256966125820776418[16] = 0.0;
   out_2256966125820776418[17] = 0.0;
   out_2256966125820776418[18] = 0.0;
   out_2256966125820776418[19] = 0.0;
   out_2256966125820776418[20] = 1.0;
   out_2256966125820776418[21] = 0.0;
   out_2256966125820776418[22] = 0.0;
   out_2256966125820776418[23] = 0.0;
   out_2256966125820776418[24] = 0.0;
   out_2256966125820776418[25] = 0.0;
   out_2256966125820776418[26] = 0.0;
   out_2256966125820776418[27] = 0.0;
   out_2256966125820776418[28] = 0.0;
   out_2256966125820776418[29] = 0.0;
   out_2256966125820776418[30] = 1.0;
   out_2256966125820776418[31] = 0.0;
   out_2256966125820776418[32] = 0.0;
   out_2256966125820776418[33] = 0.0;
   out_2256966125820776418[34] = 0.0;
   out_2256966125820776418[35] = 0.0;
   out_2256966125820776418[36] = 0.0;
   out_2256966125820776418[37] = 0.0;
   out_2256966125820776418[38] = 0.0;
   out_2256966125820776418[39] = 0.0;
   out_2256966125820776418[40] = 1.0;
   out_2256966125820776418[41] = 0.0;
   out_2256966125820776418[42] = 0.0;
   out_2256966125820776418[43] = 0.0;
   out_2256966125820776418[44] = 0.0;
   out_2256966125820776418[45] = 0.0;
   out_2256966125820776418[46] = 0.0;
   out_2256966125820776418[47] = 0.0;
   out_2256966125820776418[48] = 0.0;
   out_2256966125820776418[49] = 0.0;
   out_2256966125820776418[50] = 1.0;
   out_2256966125820776418[51] = 0.0;
   out_2256966125820776418[52] = 0.0;
   out_2256966125820776418[53] = 0.0;
   out_2256966125820776418[54] = 0.0;
   out_2256966125820776418[55] = 0.0;
   out_2256966125820776418[56] = 0.0;
   out_2256966125820776418[57] = 0.0;
   out_2256966125820776418[58] = 0.0;
   out_2256966125820776418[59] = 0.0;
   out_2256966125820776418[60] = 1.0;
   out_2256966125820776418[61] = 0.0;
   out_2256966125820776418[62] = 0.0;
   out_2256966125820776418[63] = 0.0;
   out_2256966125820776418[64] = 0.0;
   out_2256966125820776418[65] = 0.0;
   out_2256966125820776418[66] = 0.0;
   out_2256966125820776418[67] = 0.0;
   out_2256966125820776418[68] = 0.0;
   out_2256966125820776418[69] = 0.0;
   out_2256966125820776418[70] = 1.0;
   out_2256966125820776418[71] = 0.0;
   out_2256966125820776418[72] = 0.0;
   out_2256966125820776418[73] = 0.0;
   out_2256966125820776418[74] = 0.0;
   out_2256966125820776418[75] = 0.0;
   out_2256966125820776418[76] = 0.0;
   out_2256966125820776418[77] = 0.0;
   out_2256966125820776418[78] = 0.0;
   out_2256966125820776418[79] = 0.0;
   out_2256966125820776418[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_4796940968590720059) {
   out_4796940968590720059[0] = state[0];
   out_4796940968590720059[1] = state[1];
   out_4796940968590720059[2] = state[2];
   out_4796940968590720059[3] = state[3];
   out_4796940968590720059[4] = state[4];
   out_4796940968590720059[5] = dt*(stiffness_front*(-state[2] - state[3] + state[7])*state[0]/state[1] + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/state[4] + ((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4])*state[6] - 9.8100000000000005*state[8]) + state[5];
   out_4796940968590720059[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_4796940968590720059[7] = state[7];
   out_4796940968590720059[8] = state[8];
}
void F_fun(double *state, double dt, double *out_4222714394410475662) {
   out_4222714394410475662[0] = 1;
   out_4222714394410475662[1] = 0;
   out_4222714394410475662[2] = 0;
   out_4222714394410475662[3] = 0;
   out_4222714394410475662[4] = 0;
   out_4222714394410475662[5] = 0;
   out_4222714394410475662[6] = 0;
   out_4222714394410475662[7] = 0;
   out_4222714394410475662[8] = 0;
   out_4222714394410475662[9] = 0;
   out_4222714394410475662[10] = 1;
   out_4222714394410475662[11] = 0;
   out_4222714394410475662[12] = 0;
   out_4222714394410475662[13] = 0;
   out_4222714394410475662[14] = 0;
   out_4222714394410475662[15] = 0;
   out_4222714394410475662[16] = 0;
   out_4222714394410475662[17] = 0;
   out_4222714394410475662[18] = 0;
   out_4222714394410475662[19] = 0;
   out_4222714394410475662[20] = 1;
   out_4222714394410475662[21] = 0;
   out_4222714394410475662[22] = 0;
   out_4222714394410475662[23] = 0;
   out_4222714394410475662[24] = 0;
   out_4222714394410475662[25] = 0;
   out_4222714394410475662[26] = 0;
   out_4222714394410475662[27] = 0;
   out_4222714394410475662[28] = 0;
   out_4222714394410475662[29] = 0;
   out_4222714394410475662[30] = 1;
   out_4222714394410475662[31] = 0;
   out_4222714394410475662[32] = 0;
   out_4222714394410475662[33] = 0;
   out_4222714394410475662[34] = 0;
   out_4222714394410475662[35] = 0;
   out_4222714394410475662[36] = 0;
   out_4222714394410475662[37] = 0;
   out_4222714394410475662[38] = 0;
   out_4222714394410475662[39] = 0;
   out_4222714394410475662[40] = 1;
   out_4222714394410475662[41] = 0;
   out_4222714394410475662[42] = 0;
   out_4222714394410475662[43] = 0;
   out_4222714394410475662[44] = 0;
   out_4222714394410475662[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/state[1] + (-stiffness_front - stiffness_rear)*state[5]/state[4] + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/state[4]);
   out_4222714394410475662[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/pow(state[1], 2);
   out_4222714394410475662[47] = -dt*stiffness_front*state[0]/state[1];
   out_4222714394410475662[48] = -dt*stiffness_front*state[0]/state[1];
   out_4222714394410475662[49] = dt*(-(-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/pow(state[4], 2) + (-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/pow(state[4], 2) - 1)*state[6]);
   out_4222714394410475662[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/state[4] + 1;
   out_4222714394410475662[51] = dt*((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4]);
   out_4222714394410475662[52] = dt*stiffness_front*state[0]/state[1];
   out_4222714394410475662[53] = -9.8100000000000005*dt;
   out_4222714394410475662[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_4222714394410475662[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_4222714394410475662[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4222714394410475662[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4222714394410475662[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_4222714394410475662[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_4222714394410475662[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_4222714394410475662[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4222714394410475662[62] = 0;
   out_4222714394410475662[63] = 0;
   out_4222714394410475662[64] = 0;
   out_4222714394410475662[65] = 0;
   out_4222714394410475662[66] = 0;
   out_4222714394410475662[67] = 0;
   out_4222714394410475662[68] = 0;
   out_4222714394410475662[69] = 0;
   out_4222714394410475662[70] = 1;
   out_4222714394410475662[71] = 0;
   out_4222714394410475662[72] = 0;
   out_4222714394410475662[73] = 0;
   out_4222714394410475662[74] = 0;
   out_4222714394410475662[75] = 0;
   out_4222714394410475662[76] = 0;
   out_4222714394410475662[77] = 0;
   out_4222714394410475662[78] = 0;
   out_4222714394410475662[79] = 0;
   out_4222714394410475662[80] = 1;
}
void h_25(double *state, double *unused, double *out_322937802859934338) {
   out_322937802859934338[0] = state[6];
}
void H_25(double *state, double *unused, double *out_6936222100091460819) {
   out_6936222100091460819[0] = 0;
   out_6936222100091460819[1] = 0;
   out_6936222100091460819[2] = 0;
   out_6936222100091460819[3] = 0;
   out_6936222100091460819[4] = 0;
   out_6936222100091460819[5] = 0;
   out_6936222100091460819[6] = 1;
   out_6936222100091460819[7] = 0;
   out_6936222100091460819[8] = 0;
}
void h_24(double *state, double *unused, double *out_1869508837161061178) {
   out_1869508837161061178[0] = state[4];
   out_1869508837161061178[1] = state[5];
}
void H_24(double *state, double *unused, double *out_2291843085977734406) {
   out_2291843085977734406[0] = 0;
   out_2291843085977734406[1] = 0;
   out_2291843085977734406[2] = 0;
   out_2291843085977734406[3] = 0;
   out_2291843085977734406[4] = 1;
   out_2291843085977734406[5] = 0;
   out_2291843085977734406[6] = 0;
   out_2291843085977734406[7] = 0;
   out_2291843085977734406[8] = 0;
   out_2291843085977734406[9] = 0;
   out_2291843085977734406[10] = 0;
   out_2291843085977734406[11] = 0;
   out_2291843085977734406[12] = 0;
   out_2291843085977734406[13] = 0;
   out_2291843085977734406[14] = 1;
   out_2291843085977734406[15] = 0;
   out_2291843085977734406[16] = 0;
   out_2291843085977734406[17] = 0;
}
void h_30(double *state, double *unused, double *out_598131865144440227) {
   out_598131865144440227[0] = state[4];
}
void H_30(double *state, double *unused, double *out_6982825643490482599) {
   out_6982825643490482599[0] = 0;
   out_6982825643490482599[1] = 0;
   out_6982825643490482599[2] = 0;
   out_6982825643490482599[3] = 0;
   out_6982825643490482599[4] = 1;
   out_6982825643490482599[5] = 0;
   out_6982825643490482599[6] = 0;
   out_6982825643490482599[7] = 0;
   out_6982825643490482599[8] = 0;
}
void h_26(double *state, double *unused, double *out_7051213308166894115) {
   out_7051213308166894115[0] = state[7];
}
void H_26(double *state, double *unused, double *out_7769018654744034573) {
   out_7769018654744034573[0] = 0;
   out_7769018654744034573[1] = 0;
   out_7769018654744034573[2] = 0;
   out_7769018654744034573[3] = 0;
   out_7769018654744034573[4] = 0;
   out_7769018654744034573[5] = 0;
   out_7769018654744034573[6] = 0;
   out_7769018654744034573[7] = 1;
   out_7769018654744034573[8] = 0;
}
void h_27(double *state, double *unused, double *out_3030847351108621506) {
   out_3030847351108621506[0] = state[3];
}
void H_27(double *state, double *unused, double *out_9206419714674425816) {
   out_9206419714674425816[0] = 0;
   out_9206419714674425816[1] = 0;
   out_9206419714674425816[2] = 0;
   out_9206419714674425816[3] = 1;
   out_9206419714674425816[4] = 0;
   out_9206419714674425816[5] = 0;
   out_9206419714674425816[6] = 0;
   out_9206419714674425816[7] = 0;
   out_9206419714674425816[8] = 0;
}
void h_29(double *state, double *unused, double *out_5599805132805285872) {
   out_5599805132805285872[0] = state[1];
}
void H_29(double *state, double *unused, double *out_7493056987804874783) {
   out_7493056987804874783[0] = 0;
   out_7493056987804874783[1] = 1;
   out_7493056987804874783[2] = 0;
   out_7493056987804874783[3] = 0;
   out_7493056987804874783[4] = 0;
   out_7493056987804874783[5] = 0;
   out_7493056987804874783[6] = 0;
   out_7493056987804874783[7] = 0;
   out_7493056987804874783[8] = 0;
}
void h_28(double *state, double *unused, double *out_3634163235785099023) {
   out_3634163235785099023[0] = state[0];
}
void H_28(double *state, double *unused, double *out_8990056814339350582) {
   out_8990056814339350582[0] = 1;
   out_8990056814339350582[1] = 0;
   out_8990056814339350582[2] = 0;
   out_8990056814339350582[3] = 0;
   out_8990056814339350582[4] = 0;
   out_8990056814339350582[5] = 0;
   out_8990056814339350582[6] = 0;
   out_8990056814339350582[7] = 0;
   out_8990056814339350582[8] = 0;
}
void h_31(double *state, double *unused, double *out_5832509392980725791) {
   out_5832509392980725791[0] = state[8];
}
void H_31(double *state, double *unused, double *out_6905576138214500391) {
   out_6905576138214500391[0] = 0;
   out_6905576138214500391[1] = 0;
   out_6905576138214500391[2] = 0;
   out_6905576138214500391[3] = 0;
   out_6905576138214500391[4] = 0;
   out_6905576138214500391[5] = 0;
   out_6905576138214500391[6] = 0;
   out_6905576138214500391[7] = 0;
   out_6905576138214500391[8] = 1;
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
void car_err_fun(double *nom_x, double *delta_x, double *out_8135642088081730923) {
  err_fun(nom_x, delta_x, out_8135642088081730923);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8016091243247573615) {
  inv_err_fun(nom_x, true_x, out_8016091243247573615);
}
void car_H_mod_fun(double *state, double *out_2256966125820776418) {
  H_mod_fun(state, out_2256966125820776418);
}
void car_f_fun(double *state, double dt, double *out_4796940968590720059) {
  f_fun(state,  dt, out_4796940968590720059);
}
void car_F_fun(double *state, double dt, double *out_4222714394410475662) {
  F_fun(state,  dt, out_4222714394410475662);
}
void car_h_25(double *state, double *unused, double *out_322937802859934338) {
  h_25(state, unused, out_322937802859934338);
}
void car_H_25(double *state, double *unused, double *out_6936222100091460819) {
  H_25(state, unused, out_6936222100091460819);
}
void car_h_24(double *state, double *unused, double *out_1869508837161061178) {
  h_24(state, unused, out_1869508837161061178);
}
void car_H_24(double *state, double *unused, double *out_2291843085977734406) {
  H_24(state, unused, out_2291843085977734406);
}
void car_h_30(double *state, double *unused, double *out_598131865144440227) {
  h_30(state, unused, out_598131865144440227);
}
void car_H_30(double *state, double *unused, double *out_6982825643490482599) {
  H_30(state, unused, out_6982825643490482599);
}
void car_h_26(double *state, double *unused, double *out_7051213308166894115) {
  h_26(state, unused, out_7051213308166894115);
}
void car_H_26(double *state, double *unused, double *out_7769018654744034573) {
  H_26(state, unused, out_7769018654744034573);
}
void car_h_27(double *state, double *unused, double *out_3030847351108621506) {
  h_27(state, unused, out_3030847351108621506);
}
void car_H_27(double *state, double *unused, double *out_9206419714674425816) {
  H_27(state, unused, out_9206419714674425816);
}
void car_h_29(double *state, double *unused, double *out_5599805132805285872) {
  h_29(state, unused, out_5599805132805285872);
}
void car_H_29(double *state, double *unused, double *out_7493056987804874783) {
  H_29(state, unused, out_7493056987804874783);
}
void car_h_28(double *state, double *unused, double *out_3634163235785099023) {
  h_28(state, unused, out_3634163235785099023);
}
void car_H_28(double *state, double *unused, double *out_8990056814339350582) {
  H_28(state, unused, out_8990056814339350582);
}
void car_h_31(double *state, double *unused, double *out_5832509392980725791) {
  h_31(state, unused, out_5832509392980725791);
}
void car_H_31(double *state, double *unused, double *out_6905576138214500391) {
  H_31(state, unused, out_6905576138214500391);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
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
