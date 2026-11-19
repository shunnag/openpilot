#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_2637784821013310513);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_5856550254287827272);
void pose_H_mod_fun(double *state, double *out_3227534214852498246);
void pose_f_fun(double *state, double dt, double *out_4978671403187490301);
void pose_F_fun(double *state, double dt, double *out_5858485075490961391);
void pose_h_4(double *state, double *unused, double *out_1837443762224670303);
void pose_H_4(double *state, double *unused, double *out_2620547591899460475);
void pose_h_10(double *state, double *unused, double *out_7143893956583389853);
void pose_H_10(double *state, double *unused, double *out_8037125999005922999);
void pose_h_13(double *state, double *unused, double *out_612536517588929158);
void pose_H_13(double *state, double *unused, double *out_591726233432872326);
void pose_h_14(double *state, double *unused, double *out_1327653704680832289);
void pose_H_14(double *state, double *unused, double *out_1342693264440024054);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}