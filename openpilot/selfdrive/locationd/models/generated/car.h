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
void car_err_fun(double *nom_x, double *delta_x, double *out_6294158607478421115);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_1972788413430127404);
void car_H_mod_fun(double *state, double *out_8912490379935027605);
void car_f_fun(double *state, double dt, double *out_2874020368406901832);
void car_F_fun(double *state, double dt, double *out_3306591512433985146);
void car_h_25(double *state, double *unused, double *out_6915253885225084857);
void car_H_25(double *state, double *unused, double *out_4008798554750362765);
void car_h_24(double *state, double *unused, double *out_5515146325419829175);
void car_H_24(double *state, double *unused, double *out_2566773251841155336);
void car_h_30(double *state, double *unused, double *out_327425958748789694);
void car_H_30(double *state, double *unused, double *out_1490465596243114138);
void car_h_26(double *state, double *unused, double *out_616083894152872741);
void car_H_26(double *state, double *unused, double *out_7750301873624418989);
void car_h_27(double *state, double *unused, double *out_6311938000548607340);
void car_H_27(double *state, double *unused, double *out_733128474940829079);
void car_h_29(double *state, double *unused, double *out_3364212010193122379);
void car_H_29(double *state, double *unused, double *out_980234251928721954);
void car_h_28(double *state, double *unused, double *out_5735764555747095130);
void car_H_28(double *state, double *unused, double *out_6062633268998252528);
void car_h_31(double *state, double *unused, double *out_7894040660230444409);
void car_H_31(double *state, double *unused, double *out_3978152592873402337);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}