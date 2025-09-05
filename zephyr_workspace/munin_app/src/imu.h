#ifndef MUNIN_IMU_H
#define MUNIN_IMU_H

#include <stdint.h>

#define MUNIN_FACE_COUNT 6

int munin_imu_init(void);
void munin_imu_update(void);
uint8_t munin_imu_get_current_face(void);
uint32_t munin_imu_get_session_delta_s(void);

#endif
