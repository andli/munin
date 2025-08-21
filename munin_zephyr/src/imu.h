#ifndef IMU_H
#define IMU_H

#include <stdint.h>

// Face IDs (0-5)
#define MUNIN_FACE_COUNT 6

// Function prototypes
int munin_imu_init(void);
void munin_imu_update(void);
uint8_t munin_imu_get_current_face(void);
uint8_t munin_imu_get_last_settled_face(void);

#endif // IMU_H
