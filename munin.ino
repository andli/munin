/*
    Working example with:
    - Arduino 1.8.19
    - Seeed Arduino LSM6DS3 library 2.0.3 (not 2.0.4)
    - Board: Seeed nRF52 mbed-enabled Boards -> Seeed XIAO BLE Sense - nRF52840 (only available in Arduino IDE 1.x)
    - ArduinoBLE 1.4.1
*/

#include "LSM6DS3.h"
#include "Wire.h"
#include "ArduinoBLE.h"

// Custom UUIDs (examples; generate your own)
#define MUNIN_FACE_SERVICE      "6e400001-8a3a-11e5-8994-feff819cdc9f"
#define MUNIN_FACE_CHAR         "6e400002-8a3a-11e5-8994-feff819cdc9f"

// Standard Battery Service
#define BATTERY_SERVICE_UUID    "180F"
#define BATTERY_LEVEL_UUID      "2A19"

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




//Create a instance of class LSM6DS3
LSM6DS3 myIMU(I2C_MODE, 0x6A);    //I2C device address 0x6A

Vector3 prevAccel(NAN, NAN, NAN);
Vector3 prevGyro(NAN, NAN, NAN);
bool showI2Cerrors = false;
BLEService faceService("6e400001-8a3a-11e5-8994-feff819cdc9f"); // custom service UUID
BLEByteCharacteristic faceCharacteristic("6e400002-8a3a-11e5-8994-feff819cdc9f", BLERead | BLENotify); // custom characteristic UUID

void setup() {
  Serial.begin(9600);
  while (!Serial);

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

  // Init characteristics with a value
  faceCharacteristic.writeValue(0);
  
  faceService.addCharacteristic(faceCharacteristic);
  BLE.addService(faceService);
  
  BLE.setAdvertisedService(faceService);
  BLE.advertise();

  Serial.println("BLE advertising as Munin...");
}

void loop() {
  // keep BLE stack happy
  BLE.poll();
  
  Vector3 a1(myIMU.readFloatAccelX(), myIMU.readFloatAccelY(), myIMU.readFloatAccelZ());
  Vector3 g1(myIMU.readFloatGyroX(), myIMU.readFloatGyroY(), myIMU.readFloatGyroZ());

  if (a1 != prevAccel) {
    //Accelerometer
    int currentFace = getFace(a1);
    Serial.print("Upward face: ");
    Serial.println(currentFace);

    
    faceCharacteristic.writeValue((byte)currentFace);
    prevAccel = a1;
  }



  delay(1000);
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
