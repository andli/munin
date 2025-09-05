#include "imu.h"
#include "munin_protocol.h"
#include "led_effects.h"
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <math.h>
#include "debug.h"

/* Attempt to resolve the IMU device via compatible (preferred) falling back to node label. */
#if DT_HAS_COMPAT_STATUS_OKAY(st_lsm6dsl)
#define IMU_NODE DT_COMPAT_GET_ANY_STATUS_OKAY(st_lsm6dsl)
#elif DT_HAS_COMPAT_STATUS_OKAY(st_lsm6ds3tr_c)
#define IMU_NODE DT_COMPAT_GET_ANY_STATUS_OKAY(st_lsm6ds3tr_c)
#endif

#define IMU_SAMPLE_INTERVAL_MS 180      /* ~5.5 Hz sampling to save power */
#define IMU_SMOOTH_WINDOW      6        /* Moderate smoothing */
#define IMU_MIN_AXIS_G         0.55f    /* Minimum absolute g on dominant axis */
#define IMU_AXIS_MARGIN_G      0.18f    /* Dominance margin over next axis */
#define FACE_SETTLE_TIME_MS    1500     /* Require 1.5s stable before switching face */
/* Removed unused FACE_HYSTERESIS_EXTRA constant (simplified hysteresis logic) */

static const struct device *accel;
static uint8_t s_face;              /* Current accepted face */
static uint8_t s_candidate;         /* Candidate face while settling */
static int64_t s_candidate_since;   /* When candidate was first observed */
static int64_t s_session_start;     /* When current face session started */

/* Smoothing buffers */
static float hist_x[IMU_SMOOTH_WINDOW];
static float hist_y[IMU_SMOOTH_WINDOW];
static float hist_z[IMU_SMOOTH_WINDOW];
static uint8_t hist_index;
static uint8_t hist_count;

static void imu_add_sample(float x, float y, float z)
{
    hist_x[hist_index] = x; hist_y[hist_index] = y; hist_z[hist_index] = z;
    hist_index = (hist_index + 1) % IMU_SMOOTH_WINDOW;
    if (hist_count < IMU_SMOOTH_WINDOW) hist_count++;
}

static void imu_get_average(float *x, float *y, float *z)
{
    float sx=0, sy=0, sz=0;
    for (uint8_t i=0;i<hist_count;i++) { sx += hist_x[i]; sy += hist_y[i]; sz += hist_z[i]; }
    if (hist_count == 0) { *x=*y=*z=0.f; return; }
    *x = sx / hist_count; *y = sy / hist_count; *z = sz / hist_count;
}

/* Map dominant axis & sign -> face id (1..6). Return 0 if unstable/unknown. */
static uint8_t face_from_avg(float x, float y, float z)
{
    float ax = fabsf(x), ay = fabsf(y), az = fabsf(z);
    /* Find largest and second largest magnitudes */
    float max1 = ax, max2 = -1.f; int idx = 0;
    if (ay > max1) { max2 = max1; max1 = ay; idx = 1; } else { max2 = ay; }
    if (az > max1) { max2 = max1; max1 = az; idx = 2; } else if (az > max2) { max2 = az; }
    if (max1 < IMU_MIN_AXIS_G) return 0;
    if ((max1 - max2) < IMU_AXIS_MARGIN_G) return 0;
    switch (idx) {
        case 0: return (x > 0.f) ? 1 : 2; /* X */
        case 1: return (y > 0.f) ? 3 : 4; /* Y */
        default: return (z > 0.f) ? 5 : 6; /* Z */
    }
}

int munin_imu_init(void)
{
#ifdef IMU_NODE
    accel = DEVICE_DT_GET(IMU_NODE);
    printk("IMU: Resolved via compatible IMU_NODE -> %p\n", accel);
#else
    /* Fallback: legacy node label guess */
    accel = DEVICE_DT_GET_OR_NULL(DT_NODELABEL(lsm6ds3tr_c));
    printk("IMU: Fallback node label lookup -> %p\n", accel);
#endif

    if (!accel) {
        printk("IMU: Device struct missing\n");
        return -1;
    }
    if (!device_is_ready(accel)) {
        printk("IMU: Device not ready\n");
        return -1;
    }

    printk("IMU: Device ready, configuring ODR...\n");

    /* Configure accelerometer: 104 Hz, +/- 2g (adjust if needed). */
    struct sensor_value odr = { .val1 = 104, .val2 = 0 };
    int ret = sensor_attr_set(accel, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);
    printk("IMU: Set ODR 104Hz -> %d\n", ret);

    /* Full-scale attribute not applied (driver returned -EINVAL previously); skipping. */

    /* Allow sensor to apply settings */
    k_sleep(K_MSEC(50));

    struct sensor_value v[3];
    /* Retry a few times to get non-zero data */
    bool got_nonzero = false;
    for (int attempt=0; attempt<5; attempt++) {
        ret = sensor_sample_fetch(accel);
        if (ret) {
        MLOG("IMU: Sample fetch failed (attempt %d): %d\n", attempt, ret);
            k_sleep(K_MSEC(20));
            continue;
        }
        ret = sensor_channel_get(accel, SENSOR_CHAN_ACCEL_XYZ, v);
        if (ret) {
        MLOG("IMU: Channel get failed (attempt %d): %d\n", attempt, ret);
            k_sleep(K_MSEC(20));
            continue;
        }
        if (v[0].val1 || v[0].val2 || v[1].val1 || v[1].val2 || v[2].val1 || v[2].val2) {
            got_nonzero = true;
            break;
        }
    MLOG("IMU: Still zero readings (attempt %d) ...\n", attempt);
        k_sleep(K_MSEC(30));
    }

    MLOG("IMU: Raw sensor values: [%d.%06d,%d.%06d,%d.%06d] nonzero=%d\n",
          v[0].val1, v[0].val2, v[1].val1, v[1].val2, v[2].val1, v[2].val2, got_nonzero);

    float fx = sensor_value_to_double(&v[0]);
    float fy = sensor_value_to_double(&v[1]);
    float fz = sensor_value_to_double(&v[2]);
    for (int i=0;i<IMU_SMOOTH_WINDOW;i++) imu_add_sample(fx,fy,fz);
    float ax, ay, az; imu_get_average(&ax,&ay,&az);
    s_face = face_from_avg(ax,ay,az);
    if (s_face==0) s_face = 6; /* fallback if flat/unknown at boot */
    s_candidate = s_face;
    s_candidate_since = k_uptime_get();
    s_session_start = s_candidate_since;

    int xmg = (int)(ax * 1000.f);
    int ymg = (int)(ay * 1000.f);
    int zmg = (int)(az * 1000.f);
    printk("IMU: Initial face=%d avg_mg: x=%d y=%d z=%d\n", s_face, xmg, ymg, zmg);

    munin_packet_t pkt; // Boot event (face encoded in face_id)
    munin_protocol_create_packet(&pkt, MUNIN_EVENT_BOOT, 0, s_face);
    munin_protocol_send_packet(&pkt); /* Version packet sent later from main */
    return got_nonzero ? 0 : -2; /* Return -2 if still only zeros */
}

void munin_imu_update(void)
{
    if (!accel) return;
    static int64_t last;
    static int debug_counter = 0;
    int64_t now = k_uptime_get();
    if (now - last < IMU_SAMPLE_INTERVAL_MS) return; // target rate
    last = now;

    struct sensor_value v[3];
    int ret = sensor_sample_fetch(accel);
    if (ret) {
        if (debug_counter % 50 == 0) {
        MLOG("IMU: Sample fetch error: %d\n", ret);
        }
        debug_counter++;
        return;
    }
    ret = sensor_channel_get(accel, SENSOR_CHAN_ACCEL_XYZ, v);
    if (ret) {
        if (debug_counter % 50 == 0) {
        MLOG("IMU: Channel get error: %d\n", ret);
        }
        debug_counter++;
        return;
    }
    
    /* Add new sample to smoothing window */
    float fx = sensor_value_to_double(&v[0]);
    float fy = sensor_value_to_double(&v[1]);
    float fz = sensor_value_to_double(&v[2]);
    imu_add_sample(fx,fy,fz);
    float ax, ay, az; imu_get_average(&ax,&ay,&az);
    uint8_t detected = face_from_avg(ax,ay,az);
    
    // Debug output every 5 seconds
    if (MUNIN_DEBUG && (debug_counter % 30 == 0)) { /* Every ~5.4s (30 * 180ms) */
        int xmg = (int)(ax * 1000.f);
        int ymg = (int)(ay * 1000.f);
        int zmg = (int)(az * 1000.f);
        printk("IMU: avg_mg x=%d y=%d z=%d -> detected=%d current=%d cand=%d t=%lld\n", 
               xmg, ymg, zmg, detected, s_face, s_candidate, (long long)(k_uptime_get() - s_candidate_since));
    }
    debug_counter++;
    
    if (detected != 0) {
        if (detected != s_face) {
            /* If new candidate different from previous candidate, restart timer */
            if (detected != s_candidate) {
                s_candidate = detected;
                s_candidate_since = now;
                MLOG("IMU: New candidate face: %d\n", detected);
            } else {
                /* Check stability duration */
                if ((now - s_candidate_since) >= FACE_SETTLE_TIME_MS) {
                    /* Extra hysteresis: ensure dominance still present with margin */
                    if (detected == face_from_avg(ax, ay, az)) {
                        uint32_t settle_ms = (uint32_t)(now - s_candidate_since);
                        printk("IMU: Face %d -> %d (%u ms)\n", s_face, s_candidate, settle_ms);
                        s_face = s_candidate;
                        s_session_start = now;
                        /* Increase margin slightly after switch to reduce oscillations */
                        /* (We conceptually apply hysteresis by short-circuiting candidate resets below) */
                        /*
                         * Previous implementation sent BOTH a protocol face-switch packet
                         * (over the generic TX characteristic) AND a dedicated face
                         * notification via the face characteristic. The Python client then
                         * processed both, causing duplicate logs and zero-length sessions
                         * (Face changed: X -> X). To eliminate this, we now prefer to send
                         * ONLY ONE update per actual face transition:
                         *   1. Attempt BLE notification (if a client subscribed).
                         *   2. If notify not possible (no connection / not subscribed),
                         *      fall back to protocol packet so a later-connected client can
                         *      still reconstruct history if needed.
                         */
                        extern int munin_ble_notify_face(uint8_t face_id);
                        int notif_ret = munin_ble_notify_face(s_face);
                        if (notif_ret < 0) {
                            munin_packet_t pkt;
                            munin_protocol_create_packet(&pkt, MUNIN_EVENT_FACE_SWITCH, 0, s_face);
                            munin_protocol_send_packet(&pkt);
                        }
                        munin_led_face_flash(s_face);
                    }
                }
            }
        } else {
            /* On stable current face, if candidate differs but dominance weak, reset candidate */
            s_candidate = s_face;
            s_candidate_since = now; /* maintain fresh timestamp */
        }
    }

    uint32_t delta_s = (uint32_t)((now - s_session_start) / 1000);
    if (delta_s && (delta_s % 60) == 0) {
        static uint32_t last_logged = 0;
        if (delta_s != last_logged) {
            last_logged = delta_s;
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
