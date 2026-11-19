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
void car_err_fun(double *nom_x, double *delta_x, double *out_8135642088081730923);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_8016091243247573615);
void car_H_mod_fun(double *state, double *out_2256966125820776418);
void car_f_fun(double *state, double dt, double *out_4796940968590720059);
void car_F_fun(double *state, double dt, double *out_4222714394410475662);
void car_h_25(double *state, double *unused, double *out_322937802859934338);
void car_H_25(double *state, double *unused, double *out_6936222100091460819);
void car_h_24(double *state, double *unused, double *out_1869508837161061178);
void car_H_24(double *state, double *unused, double *out_2291843085977734406);
void car_h_30(double *state, double *unused, double *out_598131865144440227);
void car_H_30(double *state, double *unused, double *out_6982825643490482599);
void car_h_26(double *state, double *unused, double *out_7051213308166894115);
void car_H_26(double *state, double *unused, double *out_7769018654744034573);
void car_h_27(double *state, double *unused, double *out_3030847351108621506);
void car_H_27(double *state, double *unused, double *out_9206419714674425816);
void car_h_29(double *state, double *unused, double *out_5599805132805285872);
void car_H_29(double *state, double *unused, double *out_7493056987804874783);
void car_h_28(double *state, double *unused, double *out_3634163235785099023);
void car_H_28(double *state, double *unused, double *out_8990056814339350582);
void car_h_31(double *state, double *unused, double *out_5832509392980725791);
void car_H_31(double *state, double *unused, double *out_6905576138214500391);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}