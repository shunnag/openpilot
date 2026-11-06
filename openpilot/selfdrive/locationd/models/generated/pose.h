#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_5758895393654592547);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_1226936103861324486);
void pose_H_mod_fun(double *state, double *out_2814892848741251961);
void pose_f_fun(double *state, double dt, double *out_8661001625037563019);
void pose_F_fun(double *state, double dt, double *out_8260004715325140458);
void pose_h_4(double *state, double *unused, double *out_6076013284157106490);
void pose_H_4(double *state, double *unused, double *out_1616945366858353857);
void pose_h_10(double *state, double *unused, double *out_4519099356584783039);
void pose_H_10(double *state, double *unused, double *out_6862378656678310006);
void pose_h_13(double *state, double *unused, double *out_7637538022978350115);
void pose_H_13(double *state, double *unused, double *out_1595328458473978944);
void pose_h_14(double *state, double *unused, double *out_7888116198887489293);
void pose_H_14(double *state, double *unused, double *out_4699733799153726153);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}