/*
    Working example with:
    - Arduino 1.8.19
    - Seeed Arduino LSM6DS3 library 2.0.3 (not 2.0.4)
    - Board: Seeed nRF52 mbed-enabled Boards -> Seeed XIAO BLE Sense - nRF52840 (only available in Arduino IDE 1.x)
        Serial.print("Face switch to ");
    Serial.print(face);
    Serial.println();uinoBLE 1.4.1
*/

#include "LSM6DS3.h"
#include "Wire.h"
#include "ArduinoBLE.h"

// Custom UUIDs (examples; generate your own)
#define MUNIN_FACE_SERVICE      "6e400001-8a3a-11e5-8994-feff819cdc9f"
#define MUNIN_FACE_CHAR         "6e400002-8a3a-11e5-8994-feff819cdc9f"
#define MUNIN_LED_CONFIG_CHAR   "6e400003-8a3a-11e5-8994-feff819cdc9f"

// Standard Battery Service
#define BATTERY_SERVICE_UUID    "180F"
#define BATTERY_LEVEL_UUID      "2A19"

// LED pin (built-in RGB LED on XIAO nRF52840)
// The XIAO nRF52840 has a built-in RGB LED with these pins:
#define LED_RED    12    // Red LED pin (P0_26/LEDR)
#define LED_GREEN  13    // Green LED pin (P0_20/LEDG) 
#define LED_BLUE   14    // Blue LED pin (P0_6/LRGB)

// Face color configuration (RGB values for each face)
struct FaceColor {
  uint8_t r, g, b;
};

class Vector3 {
  public:
    float x, y, z;

    Vector3() : x(0), y(0), z(0) {}
    Vector3(float x, float y, float z) : x(x), y(y), z(z) {}

    // Vector addition
    Vector3 operator+(const Vector3& other) const {
      return Vector3(x + other.x, y + other.y, z + other.z);
    }

    // Vector subtraction
    Vector3 operator-(const Vector3& other) const {
      return Vector3(x - other.x, y - other.y, z - other.z);
    }

    // Scalar multiplication
    Vector3 operator*(float scalar) const {
      return Vector3(x * scalar, y * scalar, z * scalar);
    }

    // Comparison (approx)
    bool operator==(const Vector3& other) const {
      const float epsilon = 0.0001;
      return fabs(x - other.x) < epsilon &&
             fabs(y - other.y) < epsilon &&
             fabs(z - other.z) < epsilon;
    }

    bool operator!=(const Vector3& other) const {
      return !(*this == other);
    }

    // Vector magnitude
    float magnitude() const {
      return sqrt(x * x + y * y + z * z);
    }

    // Normalized vector
    Vector3 normalized() const {
      float mag = magnitude();
      if (mag == 0.0f) return Vector3(0, 0, 0); // avoid division by zero
      return *this * (1.0f / mag);
    }

    // Print vector
    void print() const {
      Serial.print("(");
      Serial.print(x); Serial.print(", ");
      Serial.print(y); Serial.print(", ");
      Serial.print(z); Serial.println(")");
    }
};

//Create a instance of class LSM6DS3
LSM6DS3 myIMU(I2C_MODE, 0x6A);    //I2C device address 0x6A

Vector3 prevAccel(NAN, NAN, NAN);
Vector3 prevGyro(NAN, NAN, NAN);
bool showI2Cerrors = false;

// Global face color array - must be declared after the struct
FaceColor faceColors[7] = {
  {0, 0, 0},       // Face 0 (unused)
  {255, 0, 0},     // Face 1 - Red (default)
  {0, 255, 0},     // Face 2 - Green (default)
  {0, 0, 255},     // Face 3 - Blue (default)
  {255, 255, 0},   // Face 4 - Yellow (default)
  {255, 0, 255},   // Face 5 - Magenta (default)
  {128, 128, 128}  // Face 6 - Gray (default)
};

// Face tracking
int currentFace = 0;  // Track the current face
int lastBroadcastFace = -1;  // Track the last face we broadcast
int candidateFace = -1;  // Face that might become the new face
unsigned long faceChangeTime = 0;  // When the candidate face was first detected
const unsigned long FACE_SETTLE_TIME = 1000;  // Face must be stable for 1 second

// 6-byte protocol tracking (removed session concept)
unsigned long sessionStartTime = 0;  // When current face started (millis)
bool pendingStateSync = false;  // Flag for pending state sync after connection
unsigned long stateSyncTime = 0;  // When to send state sync

// BLE Services and Characteristics
BLEService faceService("6e400001-8a3a-11e5-8994-feff819cdc9f"); // custom service UUID
BLECharacteristic faceCharacteristic("6e400002-8a3a-11e5-8994-feff819cdc9f", BLERead | BLENotify, 6); // custom characteristic UUID (6 bytes for protocol packet)
BLECharacteristic ledConfigCharacteristic("6e400003-8a3a-11e5-8994-feff819cdc9f", BLEWrite, 4); // LED config characteristic (4 bytes per face)

// Battery Service
BLEService batteryService("180F"); // Standard Battery Service UUID
BLEByteCharacteristic batteryLevelCharacteristic("2A19", BLERead | BLENotify); // Standard Battery Level UUID

// Battery monitoring variables
unsigned long lastBatteryUpdate = 0;
const unsigned long batteryUpdateInterval = 30000; // Update every 30 seconds for more responsive monitoring
// Battery monitoring
int batteryLevel = -1; // Current battery percentage (-1 = no battery/unknown)
float batteryVoltage = 0.0; // Current battery voltage
bool batteryConnected = false; // Whether battery is physically connected
bool isCharging = false;
bool wasCharging = false;
unsigned long lastChargingCheck = 0;
const unsigned long chargingCheckInterval = 5000; // Check charging status every 5 seconds

// Battery voltage thresholds (for LiPo 3.7V battery)
const float BATTERY_MIN_VOLTAGE = 3.3;  // 0% - cutoff voltage
const float BATTERY_MAX_VOLTAGE = 4.2;  // 100% - full charge voltage  
const float BATTERY_LOW_VOLTAGE = 3.5;  // Low battery warning threshold
const float BATTERY_CHARGED_VOLTAGE = 4.1; // Consider fully charged above this

// Battery monitoring - handled internally by XIAO nRF52840 and BQ25101
// No external pins needed for battery/charging detection

int getFace(const Vector3& accel) {
  float ax = accel.x;
  float ay = accel.y;
  float az = accel.z;

  float absX = fabs(ax);
  float absY = fabs(ay);
  float absZ = fabs(az);

  // Determine dominant axis
  if (absX > absY && absX > absZ) {
    return ax > 0 ? 5 : 6;
  } else if (absY > absX && absY > absZ) {
    return ay > 0 ? 3 : 4;
  } else {
    return az > 0 ? 1 : 2;
  }
}

void initLED() {
  // Initialize LED pins
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  
  // Turn off all LEDs initially (HIGH = OFF for common cathode)
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, HIGH);
  digitalWrite(LED_BLUE, HIGH);
  
  Serial.println("LED initialized - testing RGB...");
  
  // Quick test sequence: Red -> Green -> Blue -> Off
  digitalWrite(LED_RED, LOW);
  delay(200);
  digitalWrite(LED_RED, HIGH);
  
  digitalWrite(LED_GREEN, LOW);
  delay(200);
  digitalWrite(LED_GREEN, HIGH);
  
  digitalWrite(LED_BLUE, LOW);
  delay(200);
  digitalWrite(LED_BLUE, HIGH);
  
  Serial.println("LED test complete");
}

void setLEDColor(uint8_t r, uint8_t g, uint8_t b) {
  // Set RGB LED color (XIAO nRF52840 uses common cathode - LOW is ON)
  // Use digital pins for simple on/off control first
  digitalWrite(LED_RED, r > 0 ? LOW : HIGH);
  digitalWrite(LED_GREEN, g > 0 ? LOW : HIGH);
  digitalWrite(LED_BLUE, b > 0 ? LOW : HIGH);
}

void showFaceColor(int faceId) {
  if (faceId >= 1 && faceId <= 6) {
    FaceColor color = faceColors[faceId];
    setLEDColor(color.r, color.g, color.b);
  }
}

void flashFaceColor(int faceId, int duration_ms = 500) {
  // Flash the face color briefly then turn off
  showFaceColor(faceId);
  delay(duration_ms);
  setLEDColor(0, 0, 0); // Turn off
}

void sendMuninProtocolPacket(uint8_t eventType, uint32_t deltaS, uint8_t faceId) {
  // Create 6-byte Munin protocol packet: event_type, delta_s (little-endian), face_id
  uint8_t packet[6];
  packet[0] = eventType;
  packet[1] = deltaS & 0xFF;         // delta_s low byte
  packet[2] = (deltaS >> 8) & 0xFF;  // delta_s byte 2
  packet[3] = (deltaS >> 16) & 0xFF; // delta_s byte 3
  packet[4] = (deltaS >> 24) & 0xFF; // delta_s high byte
  packet[5] = faceId;
  
  // Debug: print packet bytes
  /*
  Serial.print("Sending packet: ");
  for (int i = 0; i < 6; i++) {
    if (packet[i] < 16) Serial.print("0");
    Serial.print(packet[i], HEX);
  }
  Serial.println();
  */
  
  // Send as notification
  faceCharacteristic.writeValue(packet, 6);
  
  // Log different event types appropriately
  if (eventType == 0x01) {
    Serial.print("Face switch to ");
    Serial.println(faceId);
  } else if (eventType == 0x03) {
    Serial.print("State sync: face ");
    Serial.print(faceId);
    Serial.print(" active for ");
    Serial.print(deltaS);
    Serial.println("s");
  }
}

void onLedConfigReceived(BLEDevice central, BLECharacteristic characteristic) {
  // Handle incoming LED configuration
  if (characteristic.valueLength() == 4) {
    const uint8_t* data = characteristic.value();
    uint8_t faceId = data[0];
    uint8_t r = data[1];
    uint8_t g = data[2];
    uint8_t b = data[3];
    
    if (faceId >= 1 && faceId <= 6) {
      faceColors[faceId].r = r;
      faceColors[faceId].g = g;
      faceColors[faceId].b = b;
      
      // Flash the new color briefly to confirm
      flashFaceColor(faceId, 300);
    }
  }
}

void onBLEConnected(BLEDevice central) {
  Serial.print("BLE client connected: ");
  Serial.println(central.address());
  
  // Schedule state sync to be sent after a delay to ensure client is ready
  pendingStateSync = true;
  stateSyncTime = millis() + 3000;  // 3 second delay to ensure client notifications are set up
}

void onBLEDisconnected(BLEDevice central) {
  Serial.print("BLE client disconnected: ");
  Serial.println(central.address());
}

void setup() {
  Serial.begin(9600);
  while (!Serial);

  // Initialize LED
  initLED();

  // Battery monitoring is handled internally - no pin setup needed
  
  // Take initial battery reading
  readBatteryStatus();

  int beginResp = myIMU.begin();
  if (beginResp != 0) {
    Serial.print("Device error (code ");
    Serial.print(beginResp);
    Serial.println("). Running I2C scan...");

    scanI2C();
  } else {
    Serial.println("Device OK!");
  }

  // Init BLE
  if (!BLE.begin()) {
    Serial.println("Starting BLE failed!");
    while (1);
  }

  BLE.setLocalName("Munin-0001");
  BLE.setDeviceName("Munin-0001");

  // Initialize battery level
  batteryLevelCharacteristic.writeValue(batteryLevel);
  
  // Set up LED config characteristic callback
  ledConfigCharacteristic.setEventHandler(BLEWritten, onLedConfigReceived);
  
  // Set up BLE connection event handlers
  BLE.setEventHandler(BLEConnected, onBLEConnected);
  BLE.setEventHandler(BLEDisconnected, onBLEDisconnected);
  
  // Add characteristics to services
  faceService.addCharacteristic(faceCharacteristic);
  faceService.addCharacteristic(ledConfigCharacteristic);
  batteryService.addCharacteristic(batteryLevelCharacteristic);
  
  // Add services to BLE
  BLE.addService(faceService);
  BLE.addService(batteryService);
  
  BLE.setAdvertisedService(faceService);
  BLE.advertise();

  Serial.println("BLE advertising as Munin with battery service and LED config...");
  Serial.print("Initial battery level: ");
  Serial.print(batteryLevel);
  Serial.println("%");
  
  // Detect and set initial face after a short delay to let IMU stabilize
  delay(100);
  Vector3 initialAccel(myIMU.readFloatAccelX(), myIMU.readFloatAccelY(), myIMU.readFloatAccelZ());
  currentFace = getFace(initialAccel);
  candidateFace = currentFace;
  lastBroadcastFace = currentFace;
  faceChangeTime = millis();
  
  // Initialize session tracking
  sessionStartTime = millis();
  
  Serial.print("Initial face detected: ");
  Serial.println(currentFace);
  
  // Show initial face color briefly
  flashFaceColor(currentFace, 1000);
}

void loop() {
  // keep BLE stack happy
  BLE.poll();
  
  // Check for pending state sync
  unsigned long checkTime = millis();
  if (pendingStateSync && checkTime >= stateSyncTime) {
    // Send current device state to newly connected client using state sync event type
    uint32_t deltaS = (checkTime - sessionStartTime) / 1000;
    sendMuninProtocolPacket(0x03, deltaS, lastBroadcastFace);  // 0x03 = State Sync
    
    pendingStateSync = false;  // Clear the flag
  }
  
  // Update battery level and charging status
  updateBatteryLevel();
  checkChargingStatus();
  
  Vector3 a1(myIMU.readFloatAccelX(), myIMU.readFloatAccelY(), myIMU.readFloatAccelZ());
  Vector3 g1(myIMU.readFloatGyroX(), myIMU.readFloatGyroY(), myIMU.readFloatGyroZ());

  // Get the current face based on accelerometer
  int detectedFace = getFace(a1);
  unsigned long currentTime = millis();
  
  // Face settling logic with hysteresis
  if (detectedFace != candidateFace) {
    // New face detected, start the settling timer
    candidateFace = detectedFace;
    faceChangeTime = currentTime;
  } else if (candidateFace != lastBroadcastFace && 
             (currentTime - faceChangeTime) >= FACE_SETTLE_TIME) {
    // Face has been stable for the required time, broadcast the change
    Serial.print("Face settled and changed to: ");
    Serial.println(candidateFace);
    
    // Reset session start time
    sessionStartTime = currentTime;
    
    // Send face switch as 6-byte protocol packet (event 0x01, delta 0)
    sendMuninProtocolPacket(0x01, 0, candidateFace);
    
    lastBroadcastFace = candidateFace;
    
    // Flash LED to show face change
    flashFaceColor(candidateFace, 500);
  }

  delay(100);  // Check more frequently but only broadcast on settled changes
}

void readBatteryStatus() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastBatteryUpdate >= batteryUpdateInterval) {
    // Try to detect if battery is physically connected via micro switch
    // Real implementation would read actual hardware signals
    
    // For now, simulate battery detection logic
    static int detectionAttempts = 0;
    detectionAttempts++;
    
    if (detectionAttempts <= 3) {
      // Still detecting...
      batteryConnected = false;
      batteryLevel = -1; // Unknown/no battery
      batteryVoltage = 0.0;
      Serial.println("Detecting battery connection...");
    } else {
      // After a few attempts, check for real battery
      // Read micro switch state to determine if battery is connected
      // This should be replaced with actual pin reading
      batteryConnected = true; // Replace with: digitalRead(MICRO_SWITCH_PIN)
      
      if (batteryConnected) {
        // Read actual battery level from ADC
        // This should read actual voltage and convert to percentage
        batteryLevel = 75; // Replace with actual ADC reading and conversion
        batteryVoltage = 3.7; // Replace with actual voltage measurement
        
        Serial.print("Battery connected: ");
        Serial.print(batteryLevel);
        Serial.print("% (");
        Serial.print(batteryVoltage);
        Serial.println("V)");
        
        // Check if the built-in charging LED is green/on
        // The XIAO has a charging indicator LED that shows green when charging
        // We can use this to detect charging state
        Serial.println("Note: Check charging LED - green = charging active");
        
      } else {
        batteryLevel = -1; // No battery detected
        batteryVoltage = 0.0;
        Serial.println("⚠️ No battery detected - check micro switch");
      }
    }
    
    lastBatteryUpdate = currentTime;
  }
}

void checkChargingStatus() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastChargingCheck >= chargingCheckInterval) {
    wasCharging = isCharging;
    
    // Only check charging if battery is actually connected
    if (!batteryConnected) {
      isCharging = false;
      Serial.println("No battery - cannot charge");
    } else if (batteryLevel < 0) {
      isCharging = false;
      Serial.println("Battery level unknown - cannot determine charging");
    } else {
      // Real charging detection would go here
      // For now, assume USB connected = charging (if battery < 95%)
      bool usbConnected = true; // Assume USB connected if we're running
      isCharging = usbConnected && (batteryLevel < 95);
      
      Serial.print("Battery: ");
      Serial.print(batteryLevel);
      Serial.print("%, USB charging: ");
      Serial.println(isCharging ? "YES" : "NO");
    }
    
    // Send charging status events if status changed
    if (isCharging != wasCharging) {
      if (isCharging) {
        // Charging started
        sendMuninProtocolPacket(0x13, millis() / 1000, currentFace); // 0x13 = Charging started event
        Serial.println("=== CHARGING STARTED ===");
        
        // Show charging indication with green pulsing LED
        showChargingIndication();
      } else {
        // Charging stopped
        if (batteryLevel >= 95) {
          sendMuninProtocolPacket(0x14, millis() / 1000, currentFace); // 0x14 = Fully charged event
          Serial.println("=== FULLY CHARGED ===");
          
          // Show fully charged indication
          showChargedIndication();
        } else {
          sendMuninProtocolPacket(0x15, millis() / 1000, currentFace); // 0x15 = Charging stopped event
          Serial.println("=== CHARGING STOPPED ===");
        }
      }
    }
    
    lastChargingCheck = currentTime;
  }
}

void showChargingIndication() {
  // Pulsing green LED to indicate charging
  for (int i = 0; i < 3; i++) {
    setLEDColor(0, 255, 0); // Green
    delay(200);
    setLEDColor(0, 0, 0);   // Off
    delay(200);
  }
}

void showChargedIndication() {
  // Steady green LED for 2 seconds to indicate fully charged
  setLEDColor(0, 255, 0); // Green
  delay(2000);
  setLEDColor(0, 0, 0);   // Off
}

void showLowBatteryWarning() {
  // Pulsing red LED to indicate low battery
  for (int i = 0; i < 5; i++) {
    setLEDColor(255, 0, 0); // Red
    delay(300);
    setLEDColor(0, 0, 0);   // Off
    delay(300);
  }
}

void updateBatteryLevel() {
  unsigned long currentTime = millis();
  
  // Update battery reading every 30 seconds
  if (currentTime - lastBatteryUpdate >= batteryUpdateInterval) {
    float previousVoltage = batteryVoltage;
    int previousLevel = batteryLevel;
    
    // Read actual battery status
    readBatteryStatus();
    
    // Update BLE battery characteristic (send 0 if no battery detected)
    int bleLevel = (batteryLevel < 0) ? 0 : batteryLevel;
    batteryLevelCharacteristic.writeValue(bleLevel);
    
    // Log significant changes
    if (batteryLevel < 0) {
      Serial.println("Battery: No battery connected");
    } else if (abs(batteryLevel - previousLevel) >= 5 || abs(batteryVoltage - previousVoltage) >= 0.1) {
      Serial.print("Battery: ");
      Serial.print(batteryLevel);
      Serial.print("% (");
      Serial.print(batteryVoltage);
      Serial.println("V)");
    }
    
    // Check for low battery condition
    static bool lowBatteryWarned = false;
    if (batteryVoltage <= BATTERY_LOW_VOLTAGE && !isCharging) {
      if (!lowBatteryWarned) {
        // Send low battery protocol event
        sendMuninProtocolPacket(0x12, millis() / 1000, currentFace); // 0x12 = Low battery event
        Serial.println("LOW BATTERY WARNING!");
        
        // Show visual warning
        showLowBatteryWarning();
        
        lowBatteryWarned = true;
      }
    } else if (batteryVoltage > (BATTERY_LOW_VOLTAGE + 0.1)) {
      // Reset warning when battery level recovers (with hysteresis)
      lowBatteryWarned = false;
    }
    
    lastBatteryUpdate = currentTime;
  }
}

void scanI2C() {
  Wire.begin();
  Serial.println("Scanning I2C bus...");

  int devicesFound = 0;
  for (byte address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("I2C device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      devicesFound++;
    } else if (showI2Cerrors) {
      Serial.print("I2C error at 0x");
      if (address < 16) Serial.print("0");
      Serial.print(address, HEX);
      Serial.print(": ");

      switch (error) {
        case 1: Serial.println("Data too long to fit in transmit buffer"); break;
        case 2: Serial.println("Received NACK on transmit of address"); break;
        case 3: Serial.println("Received NACK on transmit of data"); break;
        case 4: Serial.println("Other error (bus busy, timeout, etc)"); break;
        default: Serial.println("Unknown error"); break;
      }
    }
  }

  if (devicesFound == 0) {
    Serial.println("No I2C devices found.");
  } else {
    Serial.println("I2C scan complete.");
  }
}
