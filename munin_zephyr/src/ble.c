#include "ble.h"
#include "munin_protocol.h"
#include "battery.h"
#include "imu.h"
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/services/bas.h>

LOG_MODULE_REGISTER(ble, LOG_LEVEL_INF);

// Custom UUIDs for Munin service (same as Arduino version)
#define MUNIN_FACE_SERVICE_UUID      BT_UUID_128_ENCODE(0x6e400001, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)
#define MUNIN_FACE_CHAR_UUID         BT_UUID_128_ENCODE(0x6e400002, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)
#define MUNIN_LED_CONFIG_CHAR_UUID   BT_UUID_128_ENCODE(0x6e400003, 0x8a3a, 0x11e5, 0x8994, 0xfeff819cdc9f)

// UUID declarations
static struct bt_uuid_128 munin_face_service_uuid = BT_UUID_INIT_128(MUNIN_FACE_SERVICE_UUID);
static struct bt_uuid_128 munin_face_char_uuid = BT_UUID_INIT_128(MUNIN_FACE_CHAR_UUID);
static struct bt_uuid_128 munin_led_config_char_uuid = BT_UUID_INIT_128(MUNIN_LED_CONFIG_CHAR_UUID);

// Connection tracking
static struct bt_conn *current_conn = NULL;
static bool ble_connected = false;

// Face characteristic data
static uint8_t face_char_value[MUNIN_PACKET_SIZE];

// LED configuration callback
static ssize_t write_led_config(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                                const void *buf, uint16_t len, uint16_t offset,
                                uint8_t flags)
{
    if (len == 4) {
        const uint8_t *data = (const uint8_t *)buf;
        uint8_t face_id = data[0];
        uint8_t r = data[1];
        uint8_t g = data[2];
        uint8_t b = data[3];
        
        if (face_id >= 0 && face_id < MUNIN_FACE_COUNT) {
            LOG_INF("LED config received for face %u: RGB(%u,%u,%u)", face_id, r, g, b);
            // TODO: Store LED configuration and apply to LED hardware
        }
    }
    
    return len;
}

// Face characteristic read callback
static ssize_t read_face_char(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                              void *buf, uint16_t len, uint16_t offset)
{
    return bt_gatt_attr_read(conn, attr, buf, len, offset, face_char_value, sizeof(face_char_value));
}

// GATT service definition
BT_GATT_SERVICE_DEFINE(munin_face_service,
    BT_GATT_PRIMARY_SERVICE(&munin_face_service_uuid),
    
    // Face characteristic (for sending protocol packets)
    BT_GATT_CHARACTERISTIC(&munin_face_char_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           read_face_char, NULL, face_char_value),
    BT_GATT_CCC_MANAGED(&face_char_value, BT_GATT_CCC_NOTIFY),
    
    // LED configuration characteristic
    BT_GATT_CHARACTERISTIC(&munin_led_config_char_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL, write_led_config, NULL),
);

// Connection callbacks
static void connected(struct bt_conn *conn, uint8_t err)
{
    char addr[BT_ADDR_LE_STR_LEN];
    
    bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
    
    if (err) {
        LOG_ERR("Failed to connect to %s (%u)", addr, err);
        return;
    }
    
    LOG_INF("BLE client connected: %s", addr);
    current_conn = bt_conn_ref(conn);
    ble_connected = true;
    
    // Send state sync packet when client connects
    munin_packet_t packet;
    uint32_t session_time_s = k_uptime_get() / 1000;
    munin_protocol_create_packet(&packet, MUNIN_EVENT_STATE_SYNC, 
                               session_time_s, munin_imu_get_current_face());
    munin_protocol_send_packet(&packet);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    char addr[BT_ADDR_LE_STR_LEN];
    
    bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
    LOG_INF("BLE client disconnected: %s (reason %u)", addr, reason);
    
    if (current_conn) {
        bt_conn_unref(current_conn);
        current_conn = NULL;
    }
    ble_connected = false;
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
};

// Advertising data
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, MUNIN_FACE_SERVICE_UUID),
};

int munin_ble_init(void)
{
    int err;
    
    LOG_INF("Initializing BLE");
    
    // Enable Bluetooth
    err = bt_enable(NULL);
    if (err) {
        LOG_ERR("Bluetooth init failed (err %d)", err);
        return err;
    }
    LOG_INF("Bluetooth initialized");
    
    // Start advertising
    err = bt_le_adv_start(BT_LE_ADV_CONN_NAME, ad, ARRAY_SIZE(ad), NULL, 0);
    if (err) {
        LOG_ERR("Advertising failed to start (err %d)", err);
        return err;
    }
    
    LOG_INF("BLE advertising started as '%s'", CONFIG_BT_DEVICE_NAME);
    return 0;
}

void munin_ble_update(void)
{
    // Update battery service if available
    if (ble_connected) {
        uint8_t battery_level = munin_battery_get_percentage();
        bt_bas_set_battery_level(battery_level);
    }
    
    // Other BLE maintenance tasks can go here
}

int munin_ble_send_data(const uint8_t *data, size_t length)
{
    if (!ble_connected || !current_conn) {
        LOG_WRN("Cannot send data - BLE not connected");
        return -1;
    }
    
    if (length != MUNIN_PACKET_SIZE) {
        LOG_ERR("Invalid packet size: %zu (expected %d)", length, MUNIN_PACKET_SIZE);
        return -1;
    }
    
    // Copy data to characteristic value
    memcpy(face_char_value, data, length);
    
    // Notify connected client
    int err = bt_gatt_notify(current_conn, &munin_face_service.attrs[1], 
                            face_char_value, length);
    if (err) {
        LOG_ERR("Failed to send notification: %d", err);
        return err;
    }
    
    LOG_DBG("Sent %zu bytes via BLE notification", length);
    return 0;
}

bool munin_ble_is_connected(void)
{
    return ble_connected;
}
