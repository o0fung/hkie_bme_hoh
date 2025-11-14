#ifndef __SETUP_H__
#define __SETUP_H__

#define DEVICE_NAME     (char*) "RR_HOH_WR"         // BLE name
#define VERSION         (char*) "V1.0.0"            // version for product registration
#define DEVELOPMENT     (char*) "v20250217"         // version for internal reference
#define BAUDRATE        115200

#define LOOP_TIME       19995           // for high frequency work (e.g. IMU data, status update)
                                        //   50Hz, i.e. ~20ms per loop
                                        //   here I use 19995 micro-seconds, considering time overhead
#define LOOP_ONE_SEC    1000000         // for low frequency work (e.g. check connectivity)

#define SERVICE         (char*) "484f4801-4200-4c00-4500-000032303233"
#define CHAR_RX         (char*) "484f4802-4200-4c00-4500-000032303233"
#define CHAR_TX         (char*) "484f4803-4200-4c00-4500-000032303233"
#define CHAR_TX_DATA    (char*) "484f4803-4200-4c00-4500-000032303233"
#define CHAR_TX_STATUS  (char*) "484f4804-4200-4c00-4500-000032303233"
#define CHAR_TX_SETTING (char*) "484f4805-4200-4c00-4500-000032303233"

#define HB_ADRR         0x50            // address for EEPROM on hand brace to return left/right side
#define IMU_ADRR        0x68            // address for ICM20948 IMU
#define AD0_VAL         0               // select ICM20948 I2C address

#define FREQ_I2C_FOR_ICM    400000      // select frequency of I2C bus interface (suitable for ICM20948)

// #define CABLE_DETECT    17              // pin for detect power & sensing cable connection
#define CABLE_DETECT    34              // pin for detect power & sensing cable connection

#define I2C_DATA        21              // pin for I2C data (ICM20948)
#define I2C_CLOCK       22              // pin for I2C clock (ICM20948)

#define EEPROM_DATA     17              // pin for I2C data (EEPROM)
#define EEPROM_CLOCK    32              // pin for I2C clock (EEPROM)

#define SPI_MOSI        19              // pin for SPI MOSI
#define SPI_MISO        23              // pin for SPI MISO
#define SPI_CLK         30              // pin for SPI clock
#define SPI_SS1         5               // pin for SPI CS for MSP3208
#define SPI_SS2         32              // pin for SPI CS for IMU (not used)

#define ADC_VREF        3300            // ADC 2.3V Vref
#define ADC_CLK         1600000         // SPI Clock 1.6MHz
#define MSBFIRST        1
#define SPI_MODE0       0

// pins for controlling motors on the five fingers
//   activate the motor only when M_IN1 and M_IN2 are at different levels
//   flexion    when #1 is HIGH,    #2 is LOW
//   extension  when #1 is LOW,     #2 is HIGH
#define M1_IN1          33              
#define M2_IN1          26      
#define M3_IN1          14      
#define M4_IN1          13      
#define M5_IN1          4       

#define M1_IN2          25      
#define M2_IN2          27      
#define M3_IN2          12      
#define M4_IN2          15      
#define M5_IN2          16   

uint8_t M_IN[5][2] = {
    {M1_IN1, M1_IN2},
    {M2_IN1, M2_IN2},
    {M3_IN1, M3_IN2},
    {M4_IN1, M4_IN2},
    {M5_IN1, M5_IN2},
};

#endif