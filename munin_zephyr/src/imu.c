#include "imu.h"
#include "munin_protocol.h"
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/sensor.h>
#include <math.h>

LOG_MODULE_REGISTER(imu, LOG_LEVEL_INF);

// Face detection parameters
#define FACE_SETTLE_TIME_MS 2000    // Time to wait before confirming face change
#define FACE_DETECTION_THRESHOLD 0.7 // Minimum acceleration component for face detection

// IMU sampling
#define IMU_SAMPLE_INTERVAL_MS 100  // Sample IMU every 100ms

// Static variables
static const struct device *accel_dev;
static uint8_t current_face = 0;
static uint8_t candidate_face = 0;
static uint8_t last_settled_face = 0;
static int64_t face_change_time = 0;
static int64_t last_imu_sample = 0;
static int64_t session_start_time = 0;

// Face detection based on accelerometer readings
static uint8_t detect_face_from_accel(struct sensor_value *accel)
{
    // Convert sensor values to float
    float x = sensor_value_to_double(&accel[0]);
    float y = sensor_value_to_double(&accel[1]);
    float z = sensor_value_to_double(&accel[2]);
    
    // Find the axis with the largest absolute value (gravity direction)
    float abs_x = fabs(x);
    float abs_y = fabs(y);
    float abs_z = fabs(z);
    
    // Determine face based on dominant axis and sign
    // This mapping should match your cube's physical orientation
    if (abs_x > abs_y && abs_x > abs_z && abs_x > FACE_DETECTION_THRESHOLD) {
        return (x > 0) ? 1 : 2;  // Face 1 or 2
    } else if (abs_y > abs_x && abs_y > abs_z && abs_y > FACE_DETECTION_THRESHOLD) {
        return (y > 0) ? 3 : 4;  // Face 3 or 4
    } else if (abs_z > abs_x && abs_z > abs_y && abs_z > FACE_DETECTION_THRESHOLD) {
        return (z > 0) ? 5 : 0;  // Face 5 or 0
    }
    
    // If no clear dominant axis, return current face
    return current_face;
}

int munin_imu_init(void)
{
    LOG_INF("Initializing IMU");
    
    // Get accelerometer device (LSM6DSL on XIAO BLE)
    accel_dev = DEVICE_DT_GET_ONE(st_lsm6dsl);
    if (!device_is_ready(accel_dev)) {
        LOG_ERR("Accelerometer device not ready");
        return -1;
    }
    
    // Initial face detection after a short delay
    k_sleep(K_MSEC(100));
    
    struct sensor_value accel[3];
    int ret = sensor_sample_fetch(accel_dev);
    if (ret == 0) {
        ret = sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_XYZ, accel);
        if (ret == 0) {
            current_face = detect_face_from_accel(accel);
            candidate_face = current_face;
            last_settled_face = current_face;
            face_change_time = k_uptime_get();
            session_start_time = k_uptime_get();
            
            LOG_INF("Initial face detected: %u", current_face);
            
            // Send boot event
            munin_packet_t packet;
            munin_protocol_create_packet(&packet, MUNIN_EVENT_BOOT, 0, current_face);
            munin_protocol_send_packet(&packet);
        }
    }
    
    if (ret != 0) {
        LOG_ERR("Failed to read initial accelerometer data: %d", ret);
        return ret;
    }
    
    LOG_INF("IMU initialized");
    return 0;
}

void munin_imu_update(void)
{
    int64_t now = k_uptime_get();
    
    // Sample IMU at regular intervals
    if (now - last_imu_sample < IMU_SAMPLE_INTERVAL_MS) {
        return;
    }
    
    struct sensor_value accel[3];
    int ret = sensor_sample_fetch(accel_dev);
    if (ret != 0) {
        LOG_ERR("Failed to fetch sensor sample: %d", ret);
        return;
    }
    
    ret = sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_XYZ, accel);
    if (ret != 0) {
        LOG_ERR("Failed to get accelerometer data: %d", ret);
        return;
    }
    
    uint8_t detected_face = detect_face_from_accel(accel);
    
    // Check if face has changed
    if (detected_face != candidate_face) {
        // New face detected, start settle timer
        candidate_face = detected_face;
        face_change_time = now;
        LOG_DBG("Face candidate changed to: %u", candidate_face);
    } else if (candidate_face != current_face) {
        // Face candidate is stable, check if settle time has passed
        if (now - face_change_time >= FACE_SETTLE_TIME_MS) {
            // Face change confirmed
            uint8_t old_face = current_face;
            current_face = candidate_face;
            last_settled_face = current_face;
            
            LOG_INF("Face settled and changed to: %u", current_face);
            
            // Send face switch event
            munin_packet_t packet;
            munin_protocol_create_packet(&packet, MUNIN_EVENT_FACE_SWITCH, 0, current_face);
            munin_protocol_send_packet(&packet);
            
            // Reset session timer
            session_start_time = now;
        }
    } else {
        // Same face is stable, send periodic ongoing log
        uint32_t session_time_s = (uint32_t)((now - session_start_time) / 1000);
        
        // Send ongoing log every 60 seconds
        if (session_time_s > 0 && (session_time_s % 60) == 0) {
            munin_packet_t packet;
            munin_protocol_create_packet(&packet, MUNIN_EVENT_ONGOING_LOG, session_time_s, current_face);
            munin_protocol_send_packet(&packet);
            LOG_DBG("Ongoing log: face %u active for %u seconds", current_face, session_time_s);
        }
    }
    
    last_imu_sample = now;
}

uint8_t munin_imu_get_current_face(void)
{
    return current_face;
}

uint8_t munin_imu_get_last_settled_face(void)
{
    return last_settled_face;
}
