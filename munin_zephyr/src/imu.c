#include "imu.h"
#include "munin_protocol.h"
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <math.h>

#define FACE_SETTLE_TIME_MS 1500

static const struct device *accel;
static uint8_t s_face;
static uint8_t s_candidate;
static int64_t s_candidate_since;
static int64_t s_session_start;

static uint8_t face_from_accel(const struct sensor_value *v)
{
    double x = sensor_value_to_double(&((struct sensor_value *)v)[0]);
    double y = sensor_value_to_double(&((struct sensor_value *)v)[1]);
    double z = sensor_value_to_double(&((struct sensor_value *)v)[2]);
    double ax = fabs(x), ay = fabs(y), az = fabs(z);
    if (ax > ay && ax > az) return (x > 0) ? 1 : 2;
    if (ay > ax && ay > az) return (y > 0) ? 3 : 4;
    return (z > 0) ? 5 : 0;
}

int munin_imu_init(void)
{
    accel = DEVICE_DT_GET_ONE(st_lsm6dsl);
    if (!accel || !device_is_ready(accel)) return -1;
    k_sleep(K_MSEC(50));
    struct sensor_value v[3];
    if (sensor_sample_fetch(accel) || sensor_channel_get(accel, SENSOR_CHAN_ACCEL_XYZ, v)) return -1;
    s_face = s_candidate = face_from_accel(v);
    s_candidate_since = k_uptime_get();
    s_session_start = s_candidate_since;

    munin_packet_t pkt; // Boot event
    munin_protocol_create_packet(&pkt, MUNIN_EVENT_BOOT, 0, s_face);
    munin_protocol_send_packet(&pkt);
    return 0;
}

void munin_imu_update(void)
{
    if (!accel) return;
    static int64_t last;
    int64_t now = k_uptime_get();
    if (now - last < 100) return; // 10 Hz
    last = now;

    struct sensor_value v[3];
    if (sensor_sample_fetch(accel) || sensor_channel_get(accel, SENSOR_CHAN_ACCEL_XYZ, v)) return;
    uint8_t detected = face_from_accel(v);
    if (detected != s_candidate) {
        s_candidate = detected;
        s_candidate_since = now;
        return;
    }
    if (s_candidate != s_face && (now - s_candidate_since) >= FACE_SETTLE_TIME_MS) {
        s_face = s_candidate;
        s_session_start = now;
        munin_packet_t pkt;
        munin_protocol_create_packet(&pkt, MUNIN_EVENT_FACE_SWITCH, 0, s_face);
        munin_protocol_send_packet(&pkt);
    } else {
        uint32_t delta_s = (uint32_t)((now - s_session_start) / 1000);
        if (delta_s && (delta_s % 60) == 0) {
            munin_packet_t pkt;
            munin_protocol_create_packet(&pkt, MUNIN_EVENT_ONGOING_LOG, delta_s, s_face);
            munin_protocol_send_packet(&pkt);
        }
    }
}

uint8_t munin_imu_get_current_face(void)
{
    return s_face;
}

uint32_t munin_imu_get_session_delta_s(void)
{
    int64_t now = k_uptime_get();
    if (now < s_session_start) return 0;
    return (uint32_t)((now - s_session_start) / 1000);
}
