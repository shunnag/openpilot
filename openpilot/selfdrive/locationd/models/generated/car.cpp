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
void err_fun(double *nom_x, double *delta_x, double *out_6294158607478421115) {
   out_6294158607478421115[0] = delta_x[0] + nom_x[0];
   out_6294158607478421115[1] = delta_x[1] + nom_x[1];
   out_6294158607478421115[2] = delta_x[2] + nom_x[2];
   out_6294158607478421115[3] = delta_x[3] + nom_x[3];
   out_6294158607478421115[4] = delta_x[4] + nom_x[4];
   out_6294158607478421115[5] = delta_x[5] + nom_x[5];
   out_6294158607478421115[6] = delta_x[6] + nom_x[6];
   out_6294158607478421115[7] = delta_x[7] + nom_x[7];
   out_6294158607478421115[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1972788413430127404) {
   out_1972788413430127404[0] = -nom_x[0] + true_x[0];
   out_1972788413430127404[1] = -nom_x[1] + true_x[1];
   out_1972788413430127404[2] = -nom_x[2] + true_x[2];
   out_1972788413430127404[3] = -nom_x[3] + true_x[3];
   out_1972788413430127404[4] = -nom_x[4] + true_x[4];
   out_1972788413430127404[5] = -nom_x[5] + true_x[5];
   out_1972788413430127404[6] = -nom_x[6] + true_x[6];
   out_1972788413430127404[7] = -nom_x[7] + true_x[7];
   out_1972788413430127404[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_8912490379935027605) {
   out_8912490379935027605[0] = 1.0;
   out_8912490379935027605[1] = 0.0;
   out_8912490379935027605[2] = 0.0;
   out_8912490379935027605[3] = 0.0;
   out_8912490379935027605[4] = 0.0;
   out_8912490379935027605[5] = 0.0;
   out_8912490379935027605[6] = 0.0;
   out_8912490379935027605[7] = 0.0;
   out_8912490379935027605[8] = 0.0;
   out_8912490379935027605[9] = 0.0;
   out_8912490379935027605[10] = 1.0;
   out_8912490379935027605[11] = 0.0;
   out_8912490379935027605[12] = 0.0;
   out_8912490379935027605[13] = 0.0;
   out_8912490379935027605[14] = 0.0;
   out_8912490379935027605[15] = 0.0;
   out_8912490379935027605[16] = 0.0;
   out_8912490379935027605[17] = 0.0;
   out_8912490379935027605[18] = 0.0;
   out_8912490379935027605[19] = 0.0;
   out_8912490379935027605[20] = 1.0;
   out_8912490379935027605[21] = 0.0;
   out_8912490379935027605[22] = 0.0;
   out_8912490379935027605[23] = 0.0;
   out_8912490379935027605[24] = 0.0;
   out_8912490379935027605[25] = 0.0;
   out_8912490379935027605[26] = 0.0;
   out_8912490379935027605[27] = 0.0;
   out_8912490379935027605[28] = 0.0;
   out_8912490379935027605[29] = 0.0;
   out_8912490379935027605[30] = 1.0;
   out_8912490379935027605[31] = 0.0;
   out_8912490379935027605[32] = 0.0;
   out_8912490379935027605[33] = 0.0;
   out_8912490379935027605[34] = 0.0;
   out_8912490379935027605[35] = 0.0;
   out_8912490379935027605[36] = 0.0;
   out_8912490379935027605[37] = 0.0;
   out_8912490379935027605[38] = 0.0;
   out_8912490379935027605[39] = 0.0;
   out_8912490379935027605[40] = 1.0;
   out_8912490379935027605[41] = 0.0;
   out_8912490379935027605[42] = 0.0;
   out_8912490379935027605[43] = 0.0;
   out_8912490379935027605[44] = 0.0;
   out_8912490379935027605[45] = 0.0;
   out_8912490379935027605[46] = 0.0;
   out_8912490379935027605[47] = 0.0;
   out_8912490379935027605[48] = 0.0;
   out_8912490379935027605[49] = 0.0;
   out_8912490379935027605[50] = 1.0;
   out_8912490379935027605[51] = 0.0;
   out_8912490379935027605[52] = 0.0;
   out_8912490379935027605[53] = 0.0;
   out_8912490379935027605[54] = 0.0;
   out_8912490379935027605[55] = 0.0;
   out_8912490379935027605[56] = 0.0;
   out_8912490379935027605[57] = 0.0;
   out_8912490379935027605[58] = 0.0;
   out_8912490379935027605[59] = 0.0;
   out_8912490379935027605[60] = 1.0;
   out_8912490379935027605[61] = 0.0;
   out_8912490379935027605[62] = 0.0;
   out_8912490379935027605[63] = 0.0;
   out_8912490379935027605[64] = 0.0;
   out_8912490379935027605[65] = 0.0;
   out_8912490379935027605[66] = 0.0;
   out_8912490379935027605[67] = 0.0;
   out_8912490379935027605[68] = 0.0;
   out_8912490379935027605[69] = 0.0;
   out_8912490379935027605[70] = 1.0;
   out_8912490379935027605[71] = 0.0;
   out_8912490379935027605[72] = 0.0;
   out_8912490379935027605[73] = 0.0;
   out_8912490379935027605[74] = 0.0;
   out_8912490379935027605[75] = 0.0;
   out_8912490379935027605[76] = 0.0;
   out_8912490379935027605[77] = 0.0;
   out_8912490379935027605[78] = 0.0;
   out_8912490379935027605[79] = 0.0;
   out_8912490379935027605[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_2874020368406901832) {
   out_2874020368406901832[0] = state[0];
   out_2874020368406901832[1] = state[1];
   out_2874020368406901832[2] = state[2];
   out_2874020368406901832[3] = state[3];
   out_2874020368406901832[4] = state[4];
   out_2874020368406901832[5] = dt*(stiffness_front*(-state[2] - state[3] + state[7])*state[0]/state[1] + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/state[4] + ((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4])*state[6] - 9.8100000000000005*state[8]) + state[5];
   out_2874020368406901832[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_2874020368406901832[7] = state[7];
   out_2874020368406901832[8] = state[8];
}
void F_fun(double *state, double dt, double *out_3306591512433985146) {
   out_3306591512433985146[0] = 1;
   out_3306591512433985146[1] = 0;
   out_3306591512433985146[2] = 0;
   out_3306591512433985146[3] = 0;
   out_3306591512433985146[4] = 0;
   out_3306591512433985146[5] = 0;
   out_3306591512433985146[6] = 0;
   out_3306591512433985146[7] = 0;
   out_3306591512433985146[8] = 0;
   out_3306591512433985146[9] = 0;
   out_3306591512433985146[10] = 1;
   out_3306591512433985146[11] = 0;
   out_3306591512433985146[12] = 0;
   out_3306591512433985146[13] = 0;
   out_3306591512433985146[14] = 0;
   out_3306591512433985146[15] = 0;
   out_3306591512433985146[16] = 0;
   out_3306591512433985146[17] = 0;
   out_3306591512433985146[18] = 0;
   out_3306591512433985146[19] = 0;
   out_3306591512433985146[20] = 1;
   out_3306591512433985146[21] = 0;
   out_3306591512433985146[22] = 0;
   out_3306591512433985146[23] = 0;
   out_3306591512433985146[24] = 0;
   out_3306591512433985146[25] = 0;
   out_3306591512433985146[26] = 0;
   out_3306591512433985146[27] = 0;
   out_3306591512433985146[28] = 0;
   out_3306591512433985146[29] = 0;
   out_3306591512433985146[30] = 1;
   out_3306591512433985146[31] = 0;
   out_3306591512433985146[32] = 0;
   out_3306591512433985146[33] = 0;
   out_3306591512433985146[34] = 0;
   out_3306591512433985146[35] = 0;
   out_3306591512433985146[36] = 0;
   out_3306591512433985146[37] = 0;
   out_3306591512433985146[38] = 0;
   out_3306591512433985146[39] = 0;
   out_3306591512433985146[40] = 1;
   out_3306591512433985146[41] = 0;
   out_3306591512433985146[42] = 0;
   out_3306591512433985146[43] = 0;
   out_3306591512433985146[44] = 0;
   out_3306591512433985146[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/state[1] + (-stiffness_front - stiffness_rear)*state[5]/state[4] + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/state[4]);
   out_3306591512433985146[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/pow(state[1], 2);
   out_3306591512433985146[47] = -dt*stiffness_front*state[0]/state[1];
   out_3306591512433985146[48] = -dt*stiffness_front*state[0]/state[1];
   out_3306591512433985146[49] = dt*(-(-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/pow(state[4], 2) + (-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/pow(state[4], 2) - 1)*state[6]);
   out_3306591512433985146[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/state[4] + 1;
   out_3306591512433985146[51] = dt*((-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/state[4] - state[4]);
   out_3306591512433985146[52] = dt*stiffness_front*state[0]/state[1];
   out_3306591512433985146[53] = -9.8100000000000005*dt;
   out_3306591512433985146[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_3306591512433985146[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_3306591512433985146[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3306591512433985146[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3306591512433985146[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_3306591512433985146[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_3306591512433985146[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_3306591512433985146[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_3306591512433985146[62] = 0;
   out_3306591512433985146[63] = 0;
   out_3306591512433985146[64] = 0;
   out_3306591512433985146[65] = 0;
   out_3306591512433985146[66] = 0;
   out_3306591512433985146[67] = 0;
   out_3306591512433985146[68] = 0;
   out_3306591512433985146[69] = 0;
   out_3306591512433985146[70] = 1;
   out_3306591512433985146[71] = 0;
   out_3306591512433985146[72] = 0;
   out_3306591512433985146[73] = 0;
   out_3306591512433985146[74] = 0;
   out_3306591512433985146[75] = 0;
   out_3306591512433985146[76] = 0;
   out_3306591512433985146[77] = 0;
   out_3306591512433985146[78] = 0;
   out_3306591512433985146[79] = 0;
   out_3306591512433985146[80] = 1;
}
void h_25(double *state, double *unused, double *out_6915253885225084857) {
   out_6915253885225084857[0] = state[6];
}
void H_25(double *state, double *unused, double *out_4008798554750362765) {
   out_4008798554750362765[0] = 0;
   out_4008798554750362765[1] = 0;
   out_4008798554750362765[2] = 0;
   out_4008798554750362765[3] = 0;
   out_4008798554750362765[4] = 0;
   out_4008798554750362765[5] = 0;
   out_4008798554750362765[6] = 1;
   out_4008798554750362765[7] = 0;
   out_4008798554750362765[8] = 0;
}
void h_24(double *state, double *unused, double *out_5515146325419829175) {
   out_5515146325419829175[0] = state[4];
   out_5515146325419829175[1] = state[5];
}
void H_24(double *state, double *unused, double *out_2566773251841155336) {
   out_2566773251841155336[0] = 0;
   out_2566773251841155336[1] = 0;
   out_2566773251841155336[2] = 0;
   out_2566773251841155336[3] = 0;
   out_2566773251841155336[4] = 1;
   out_2566773251841155336[5] = 0;
   out_2566773251841155336[6] = 0;
   out_2566773251841155336[7] = 0;
   out_2566773251841155336[8] = 0;
   out_2566773251841155336[9] = 0;
   out_2566773251841155336[10] = 0;
   out_2566773251841155336[11] = 0;
   out_2566773251841155336[12] = 0;
   out_2566773251841155336[13] = 0;
   out_2566773251841155336[14] = 1;
   out_2566773251841155336[15] = 0;
   out_2566773251841155336[16] = 0;
   out_2566773251841155336[17] = 0;
}
void h_30(double *state, double *unused, double *out_327425958748789694) {
   out_327425958748789694[0] = state[4];
}
void H_30(double *state, double *unused, double *out_1490465596243114138) {
   out_1490465596243114138[0] = 0;
   out_1490465596243114138[1] = 0;
   out_1490465596243114138[2] = 0;
   out_1490465596243114138[3] = 0;
   out_1490465596243114138[4] = 1;
   out_1490465596243114138[5] = 0;
   out_1490465596243114138[6] = 0;
   out_1490465596243114138[7] = 0;
   out_1490465596243114138[8] = 0;
}
void h_26(double *state, double *unused, double *out_616083894152872741) {
   out_616083894152872741[0] = state[7];
}
void H_26(double *state, double *unused, double *out_7750301873624418989) {
   out_7750301873624418989[0] = 0;
   out_7750301873624418989[1] = 0;
   out_7750301873624418989[2] = 0;
   out_7750301873624418989[3] = 0;
   out_7750301873624418989[4] = 0;
   out_7750301873624418989[5] = 0;
   out_7750301873624418989[6] = 0;
   out_7750301873624418989[7] = 1;
   out_7750301873624418989[8] = 0;
}
void h_27(double *state, double *unused, double *out_6311938000548607340) {
   out_6311938000548607340[0] = state[3];
}
void H_27(double *state, double *unused, double *out_733128474940829079) {
   out_733128474940829079[0] = 0;
   out_733128474940829079[1] = 0;
   out_733128474940829079[2] = 0;
   out_733128474940829079[3] = 1;
   out_733128474940829079[4] = 0;
   out_733128474940829079[5] = 0;
   out_733128474940829079[6] = 0;
   out_733128474940829079[7] = 0;
   out_733128474940829079[8] = 0;
}
void h_29(double *state, double *unused, double *out_3364212010193122379) {
   out_3364212010193122379[0] = state[1];
}
void H_29(double *state, double *unused, double *out_980234251928721954) {
   out_980234251928721954[0] = 0;
   out_980234251928721954[1] = 1;
   out_980234251928721954[2] = 0;
   out_980234251928721954[3] = 0;
   out_980234251928721954[4] = 0;
   out_980234251928721954[5] = 0;
   out_980234251928721954[6] = 0;
   out_980234251928721954[7] = 0;
   out_980234251928721954[8] = 0;
}
void h_28(double *state, double *unused, double *out_5735764555747095130) {
   out_5735764555747095130[0] = state[0];
}
void H_28(double *state, double *unused, double *out_6062633268998252528) {
   out_6062633268998252528[0] = 1;
   out_6062633268998252528[1] = 0;
   out_6062633268998252528[2] = 0;
   out_6062633268998252528[3] = 0;
   out_6062633268998252528[4] = 0;
   out_6062633268998252528[5] = 0;
   out_6062633268998252528[6] = 0;
   out_6062633268998252528[7] = 0;
   out_6062633268998252528[8] = 0;
}
void h_31(double *state, double *unused, double *out_7894040660230444409) {
   out_7894040660230444409[0] = state[8];
}
void H_31(double *state, double *unused, double *out_3978152592873402337) {
   out_3978152592873402337[0] = 0;
   out_3978152592873402337[1] = 0;
   out_3978152592873402337[2] = 0;
   out_3978152592873402337[3] = 0;
   out_3978152592873402337[4] = 0;
   out_3978152592873402337[5] = 0;
   out_3978152592873402337[6] = 0;
   out_3978152592873402337[7] = 0;
   out_3978152592873402337[8] = 1;
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
void car_err_fun(double *nom_x, double *delta_x, double *out_6294158607478421115) {
  err_fun(nom_x, delta_x, out_6294158607478421115);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_1972788413430127404) {
  inv_err_fun(nom_x, true_x, out_1972788413430127404);
}
void car_H_mod_fun(double *state, double *out_8912490379935027605) {
  H_mod_fun(state, out_8912490379935027605);
}
void car_f_fun(double *state, double dt, double *out_2874020368406901832) {
  f_fun(state,  dt, out_2874020368406901832);
}
void car_F_fun(double *state, double dt, double *out_3306591512433985146) {
  F_fun(state,  dt, out_3306591512433985146);
}
void car_h_25(double *state, double *unused, double *out_6915253885225084857) {
  h_25(state, unused, out_6915253885225084857);
}
void car_H_25(double *state, double *unused, double *out_4008798554750362765) {
  H_25(state, unused, out_4008798554750362765);
}
void car_h_24(double *state, double *unused, double *out_5515146325419829175) {
  h_24(state, unused, out_5515146325419829175);
}
void car_H_24(double *state, double *unused, double *out_2566773251841155336) {
  H_24(state, unused, out_2566773251841155336);
}
void car_h_30(double *state, double *unused, double *out_327425958748789694) {
  h_30(state, unused, out_327425958748789694);
}
void car_H_30(double *state, double *unused, double *out_1490465596243114138) {
  H_30(state, unused, out_1490465596243114138);
}
void car_h_26(double *state, double *unused, double *out_616083894152872741) {
  h_26(state, unused, out_616083894152872741);
}
void car_H_26(double *state, double *unused, double *out_7750301873624418989) {
  H_26(state, unused, out_7750301873624418989);
}
void car_h_27(double *state, double *unused, double *out_6311938000548607340) {
  h_27(state, unused, out_6311938000548607340);
}
void car_H_27(double *state, double *unused, double *out_733128474940829079) {
  H_27(state, unused, out_733128474940829079);
}
void car_h_29(double *state, double *unused, double *out_3364212010193122379) {
  h_29(state, unused, out_3364212010193122379);
}
void car_H_29(double *state, double *unused, double *out_980234251928721954) {
  H_29(state, unused, out_980234251928721954);
}
void car_h_28(double *state, double *unused, double *out_5735764555747095130) {
  h_28(state, unused, out_5735764555747095130);
}
void car_H_28(double *state, double *unused, double *out_6062633268998252528) {
  H_28(state, unused, out_6062633268998252528);
}
void car_h_31(double *state, double *unused, double *out_7894040660230444409) {
  h_31(state, unused, out_7894040660230444409);
}
void car_H_31(double *state, double *unused, double *out_3978152592873402337) {
  H_31(state, unused, out_3978152592873402337);
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
