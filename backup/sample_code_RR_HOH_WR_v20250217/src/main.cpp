// system libraries
#include <Arduino.h>            // program based on Arduino
#include <Preferences.h>        // access flash memory of ESP32
#include <Wire.h>               // access I2C of ESP32
#include <SPI.h>                // access SPI of ESP32

// third parties libraries
#include "NimBLEDevice.h"       // control BLE in ESP32
#include "ICM_20948.h"          // control IMU data collection
#include "Mcp320x.h"            // ADC to meausre motor driven current

// user defined libraries
#include "setup.h"              // define constants
#include "../lib/Data/Data.h"               // define class to store data captured
#include "../lib/COMM/COMM.h"               // define class to decode BLE data packets
#include "../lib/BLE/BLE.h"                // define class to work with BLE communication
#include "../lib/IMU/IMU.h"                // define class to work on IMU data
#include "../lib/Motor/Motor.h"              // define class to control motors and output patterns
#include "../lib/Memory/Memory.h"             // define class to access non-volatile memory
#include "../lib/System/System.h"             // define classes to work on general system maintenance

Memory memory;                          // for access non-volatile memory
MCP3208 adc(ADC_VREF, SPI_SS1);         // for access motor current measurement
ICM_20948_I2C icm;                      // for access IMU data collection and processing
System sys;                             // for general system maintenance
Motor motor(&sys, &memory);             // for control motor output
static ServerCallback server_callback;                  // for BLE services
static CharacteristicCallback characteristic_callback;  // for BLE characteristics
Cable cable;                            // for access cable connectivity
Brace brace;                            // for access brace connectivity and left/side hand
IMU imu(&icm, &memory);                 // for IMU data collection and processing
COMM comm(&motor, &sys, &imu);          // for monitor BLE data packet encoding and decoding
BLE ble(&motor, &comm);                 // for monitor BLE services and characteristics

uint32_t timer1 = micros();             // LOOPTIME, high frequency (50Hz)
uint32_t timer2 = micros();             // LOOP_ONE_SEC, low frequency (1Hz)
uint16_t counter = 0;                   // increment counter for detecting frame missing

void setup() {

    // initiate I2C for communication with ICM20948 and EEPROM (for left/right brace detection)
    Wire.begin(I2C_DATA, I2C_CLOCK, FREQ_I2C_FOR_ICM);
    Wire1.begin(EEPROM_DATA, EEPROM_CLOCK, FREQ_I2C_FOR_ICM);
    
    Serial.begin(BAUDRATE);  // mainly for display debug message

    // initiate ESP32 onboard flash memory
    // allocated to store some non-volatile memory
    memory.init(DEVICE_NAME);           

    // initiate ADC for measure motor current (for motor collision detection)
    motor.init_adc(&adc);
    motor.init_cur_read(SPI_SS1);
    // initiate motor control parameters 
    motor.init_mot_ctrl(M_IN);
    motor.init_control();
    // due to unknown PCB fault, two fingers will start moving upon PCB board reboot
    //   middle finger will flex and ring finger will extend
    //   one solution is to trigger another movement immediately after reboot
    motor.reset_to_flexion();           // to hide the early finger movement at reboot
    
    // initiate SPI for communicate with driver to measure motor current
    SPISettings settings(ADC_CLK, MSBFIRST, SPI_MODE0);
    SPI.begin();
    SPI.beginTransaction(settings);

    // initiate ESP onboard BLE functionality
    NimBLEDevice::init(DEVICE_NAME);
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);
    // initiate BLE services and characteristics
    ble.init_service(DEVICE_NAME, SERVICE);
    ble.init_uuid(CHAR_RX, CHAR_TX);
    ble.init_callback(&server_callback, &characteristic_callback);
    ble.init_mac_address();
    // start BLE scanning and ready to pair
    ble.begin();
    // configure BLE services and characteristics
    server_callback.init(&ble, &motor);
    characteristic_callback.init(&comm);
    
    // initate general system settings
    sys.init();
    sys.set_version(VERSION);           // setup robot version info
    sys.set_development(DEVELOPMENT);
    sys.set_enable_development(false);  // select data return packets
    sys.set_enable_version(false);
    sys.set_enable_setting(false);
    sys.set_enable_status(true);
    sys.set_enable_data(true);

    cable.init(CABLE_DETECT);           // initiate cable detection
    brace.init(Wire1, HB_ADRR);         // initiate brace and left/right side detection

    imu.init(Wire, IMU_ADRR, AD0_VAL);  // initate IMU data acquisition

    Serial.print(">> ");
    Serial.print(DEVICE_NAME);
    Serial.println(" Started...");

    motor.reset_to_extension();         // to reset all fingers to extended position at start
}

void loop() {

    // tasks that performed frequently
    if (sys.check_time(&timer1, LOOP_TIME)) {
        sys.count_up();                 // update increment counter

        // state machine for motor control
        // monitor motor output per frame in loop
        switch (motor.get_state()) {

            case Motor::RESET_FLEX:
                // reset motor to full flexion position
                motor.loop_reset(false);
                break;

            case Motor::RESET_EXT:
                // reset motor to full extension position
                motor.loop_reset(true);
                break;

            case Motor::CALIBRATE:
                // count the time needed for motor to move one full ROM
                // motor move from full extension to full flexion
                motor.loop_calibration();
                break;

            case Motor::FREE:
                // motor was tasked to reach arbitary target position
                motor.loop_free();
                break;

            case Motor::CPM:
            case Motor::CPM_SEQ:
            case Motor::CPM_SEQ_REV:
            case Motor::CPM_ONCE:
                // motor was tasked to move in cycle back and forth
                // with different movement pattern
                motor.loop_cpm();
                break;

            case Motor::IDLE:
            default:
                // motor in idle state, do nothing
                break;
        }

        // send motor state and finger status
        if (sys.get_enable_status()) {
            ble.send_status();
        }

        // update and process IMU data
        // send motion sensor data
        if (sys.get_enable_data()) {
            imu.update();
            if (imu.get_working()) {
                sys.get_time_diff(&timer1);  // monitor time taken in the current frame cycle
                ble.send_data();
            }
        }
    }

    // tasks that performed once every second
    if (sys.check_time(&timer2, LOOP_ONE_SEC)) {

        // update connectivity status
        cable.check(&sys.status);
        if (brace.check_conn(&sys.status)) {
            brace.check_side(&sys.status);
        }

        // send version or setting info if requested
        // only send once per request
        if (sys.get_enable_version()) {
            // version for product registration
            ble.send_version();
            sys.set_enable_version(false);
        }
        if (sys.get_enable_development()) {
            // version for internet version control (i.e. developmennt version)
            ble.send_development();
            sys.set_enable_development(false);
        }
        if (sys.get_enable_yaw_cal()) {
            // one-shot yaw calibration query response
            ble.send_yaw_cal();
            sys.set_enable_yaw_cal(false);
        }
        if (sys.get_enable_setting()) {
            // return debug message
            ble.send_setting();
            sys.set_enable_setting(false);
        }

        // detect availability of debug message from Serial UART port
        comm.receive_serial();
    }
}
