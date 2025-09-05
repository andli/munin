#include "ble.h"
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>

// UUIDs (random custom)
#define MUNIN_SVC_UUID    BT_UUID_128_ENCODE(0x6e400001, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)
#define MUNIN_TX_UUID     BT_UUID_128_ENCODE(0x6e400002, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)
#define MUNIN_LED_UUID    BT_UUID_128_ENCODE(0x6e400003, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)

static struct bt_uuid_128 svc_uuid = BT_UUID_INIT_128(MUNIN_SVC_UUID);
static struct bt_uuid_128 tx_uuid  = BT_UUID_INIT_128(MUNIN_TX_UUID);
static struct bt_uuid_128 led_uuid = BT_UUID_INIT_128(MUNIN_LED_UUID);

static struct bt_conn *s_conn;
static uint8_t tx_value[6];
static bool ble_connected;

static ssize_t read_tx(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                       uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, tx_value, sizeof(tx_value));
}

static ssize_t write_led(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    ARG_UNUSED(attr);
    // Expect 4 bytes: face_id, r, g, b
    if (len == 4) {
        // TODO: store LED config and show feedback via LED
    }
    return len;
}

BT_GATT_SERVICE_DEFINE(munin_svc,
    BT_GATT_PRIMARY_SERVICE(&svc_uuid),
    BT_GATT_CHARACTERISTIC(&tx_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           read_tx, NULL, tx_value),
    BT_GATT_CCC(NULL, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&led_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL, write_led, NULL),
);

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) {
        return;
    }
    s_conn = bt_conn_ref(conn);
    ble_connected = true;
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(reason);
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

int munin_ble_init(void)
{
    int err = bt_enable(NULL);
    if (err) return err;
    return bt_le_adv_start(BT_LE_ADV_CONN, ad, ARRAY_SIZE(ad), NULL, 0);
}

void munin_ble_update(void)
{
    // Placeholder for future updates
}

int munin_ble_send_data(const uint8_t *data, size_t length)
{
    if (!ble_connected || !s_conn || length == 0) return -1;
    if (length > sizeof(tx_value)) length = sizeof(tx_value);
    memcpy(tx_value, data, length);
    return bt_gatt_notify(s_conn, &munin_svc.attrs[1], tx_value, length);
}

bool munin_ble_is_connected(void)
{
    return ble_connected;
}
