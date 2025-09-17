// Clean, fixed implementation
#include "ble.h"
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/addr.h>
#include <zephyr/settings/settings.h>

// Custom 128-bit UUIDs
#define MUNIN_SVC_UUID    BT_UUID_128_ENCODE(0x6e400001, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)
#define MUNIN_TX_UUID     BT_UUID_128_ENCODE(0x6e400002, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f) /* Generic data / legacy */
#define MUNIN_LED_UUID    BT_UUID_128_ENCODE(0x6e400003, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f) /* Placeholder write */
#define MUNIN_FACE_UUID   BT_UUID_128_ENCODE(0x6e400004, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f) /* New face notify */

static struct bt_uuid_128 svc_uuid  = BT_UUID_INIT_128(MUNIN_SVC_UUID);
static struct bt_uuid_128 tx_uuid   = BT_UUID_INIT_128(MUNIN_TX_UUID);
static struct bt_uuid_128 led_uuid  = BT_UUID_INIT_128(MUNIN_LED_UUID);
static struct bt_uuid_128 face_uuid = BT_UUID_INIT_128(MUNIN_FACE_UUID);

static struct bt_conn *s_conn;
static uint8_t tx_value[8]; /* small generic buffer */
static uint8_t face_value;  /* last notified face */
static bool ble_connected;
static bool ble_advertising;
static bool face_notif_enabled; /* client subscribed */

/* Attribute index map (order produced by BT_GATT_SERVICE_DEFINE) */
#define MUNIN_SVC_ATTR_PRIMARY     0
#define MUNIN_SVC_ATTR_TX_DECL     1
#define MUNIN_SVC_ATTR_TX_VALUE    2
#define MUNIN_SVC_ATTR_TX_CCC      3
#define MUNIN_SVC_ATTR_FACE_DECL   4
#define MUNIN_SVC_ATTR_FACE_VALUE  5
#define MUNIN_SVC_ATTR_FACE_CCC    6
#define MUNIN_SVC_ATTR_LED_DECL    7
#define MUNIN_SVC_ATTR_LED_VALUE   8

static ssize_t read_tx(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                       void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, tx_value, sizeof(tx_value));
}

static ssize_t read_face(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         void *buf, uint16_t len, uint16_t offset)
{
    /* Always return the current face from IMU */
    extern uint8_t munin_imu_get_current_face(void);
    face_value = munin_imu_get_current_face();
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &face_value, sizeof(face_value));
}

static ssize_t write_led(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    ARG_UNUSED(conn); ARG_UNUSED(attr); ARG_UNUSED(flags);
    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (len != 4) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    const uint8_t *p = (const uint8_t *)buf;
    uint8_t face = p[0];
    if (face < 1 || face > 6) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }

    /* Log receipt of face color configuration packet */
    printk("cfg face=%u rgb=%u,%u,%u\n", face, p[1], p[2], p[3]);
    extern void munin_led_set_face_color(uint8_t face, uint8_t r, uint8_t g, uint8_t b);
    munin_led_set_face_color(face, p[1], p[2], p[3]);

    /* Optional: brief confirmation flash could be triggered here, but we rely on next face change */
    return len;
}

/* CCC callback for face notifications */
static void face_ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    face_notif_enabled = (value == BT_GATT_CCC_NOTIFY);
    printk("[BLE] Face notifications %s\n", face_notif_enabled ? "ENABLED" : "DISABLED");
    
    /* When notifications are enabled, send current face after a short delay */
    if (face_notif_enabled && ble_connected && s_conn) {
        /* We'll send the current face in munin_ble_update() or a separate function */
        printk("[BLE] Will send current face on next update\n");
    }
}

BT_GATT_SERVICE_DEFINE(munin_svc,
    BT_GATT_PRIMARY_SERVICE(&svc_uuid),
    /* Generic tiny data characteristic (legacy) */
    BT_GATT_CHARACTERISTIC(&tx_uuid.uuid,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ,
        read_tx, NULL, tx_value),
    BT_GATT_CCC(NULL, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    /* Face state characteristic: read current face & subscribe */
    BT_GATT_CHARACTERISTIC(&face_uuid.uuid,
        BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ,
        read_face, NULL, &face_value),
    BT_GATT_CCC(face_ccc_cfg_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    /* LED control placeholder */
    BT_GATT_CHARACTERISTIC(&led_uuid.uuid,
        BT_GATT_CHRC_WRITE,
        BT_GATT_PERM_WRITE,
        NULL, write_led, NULL),
);

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) {
        printk("[BLE] Connection failed (%u)\n", err);
        return;
    }
    s_conn = bt_conn_ref(conn);
    ble_connected = true;
    printk("[BLE] Connected\n");
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(conn);
    printk("[BLE] Disconnected (reason 0x%02x)\n", reason);
    if (s_conn) {
        bt_conn_unref(s_conn);
        s_conn = NULL;
    }
    ble_connected = false;
}

BT_CONN_CB_DEFINE(conn_cbs) = {
    .connected = connected,
    .disconnected = disconnected,
};

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, MUNIN_SVC_UUID),
};

static const struct bt_le_adv_param adv_params = BT_LE_ADV_PARAM_INIT(
    BT_LE_ADV_OPT_CONNECTABLE,
    BT_GAP_ADV_FAST_INT_MIN_2,
    BT_GAP_ADV_FAST_INT_MAX_2,
    NULL);

int munin_ble_init(void)
{
    printk("[BLE] Init start\n");

    /* Ensure an identity exists BEFORE enabling controller if settings did not provide one */
    bt_addr_le_t addrs_pre[CONFIG_BT_ID_MAX];
    size_t pre_cnt = ARRAY_SIZE(addrs_pre);
    bt_id_get(addrs_pre, &pre_cnt);
    if (pre_cnt == 0) {
        /* Create a deterministic static random address (C0:FF:EE:12:34:56) */
        bt_addr_le_t static_id = { .type = BT_ADDR_LE_RANDOM };
        static_id.a.val[0] = 0x56;
        static_id.a.val[1] = 0x34;
        static_id.a.val[2] = 0x12;
        static_id.a.val[3] = 0xEE;
        static_id.a.val[4] = 0xFF;
        static_id.a.val[5] = 0xC0; /* Top two bits 1 1 => static random */
        int id_ret = bt_id_create(&static_id, NULL);
        if (id_ret < 0) {
            printk("[BLE] bt_id_create (pre-enable) failed: %d\n", id_ret);
        } else {
            printk("[BLE] Created static identity (pre-enable) id=%d\n", id_ret);
        }
    }

    int err = bt_enable(NULL); // synchronous
    if (err) {
        printk("[BLE] bt_enable failed: %d\n", err);
        return err;
    }
    printk("[BLE] bt_enable OK\n");

    bt_addr_le_t addrs[CONFIG_BT_ID_MAX];
    size_t count = ARRAY_SIZE(addrs);
    bt_id_get(addrs, &count);
    printk("[BLE] Identity count: %u\n", (unsigned)count);
    for (size_t i = 0; i < count; i++) {
        char buf[BT_ADDR_LE_STR_LEN];
        bt_addr_le_to_str(&addrs[i], buf, sizeof(buf));
        printk("[BLE] ID %u: %s\n", (unsigned)i, buf);
    }

    err = bt_le_adv_start(&adv_params, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        printk("[BLE] bt_le_adv_start failed: %d\n", err);
        return err;
    }
    ble_advertising = true;
    printk("[BLE] Advertising started\n");
    
    /* Initialize face value with current face */
    extern uint8_t munin_imu_get_current_face(void);
    face_value = munin_imu_get_current_face();
    printk("[BLE] Initialized with current face: %u\n", face_value);
    
    return 0;
}

void munin_ble_update(void)
{
    /* Send current face if notifications just got enabled */
    static bool sent_initial_face = false;
    if (face_notif_enabled && ble_connected && s_conn && !sent_initial_face) {
        extern uint8_t munin_imu_get_current_face(void);
        uint8_t current_face = munin_imu_get_current_face();
        if (current_face > 0) {
            face_value = current_face;
            int ret = bt_gatt_notify(s_conn, &munin_svc.attrs[MUNIN_SVC_ATTR_FACE_VALUE], &face_value, sizeof(face_value));
            if (ret == 0) {
                printk("[BLE] Sent current face on notification enable: %u\n", current_face);
                sent_initial_face = true;
            }
        }
    }
    
    /* Reset flag when notifications are disabled */
    if (!face_notif_enabled) {
        sent_initial_face = false;
    }
}

int munin_ble_send_data(const uint8_t *data, size_t length)
{
    if (!ble_connected || !s_conn || length == 0) return -1;
    if (length > sizeof(tx_value)) length = sizeof(tx_value);
    memcpy(tx_value, data, length);
    return bt_gatt_notify(s_conn, &munin_svc.attrs[MUNIN_SVC_ATTR_TX_VALUE], tx_value, length);
}

int munin_ble_notify_face(uint8_t face_id)
{
    if (!ble_connected || !s_conn || !face_notif_enabled) return -1;
    face_value = face_id;
    return bt_gatt_notify(s_conn, &munin_svc.attrs[MUNIN_SVC_ATTR_FACE_VALUE], &face_value, sizeof(face_value));
}

bool munin_ble_is_connected(void)
{
    return ble_connected;
}

bool munin_ble_is_advertising(void)
{
    return ble_advertising && !ble_connected;
}
