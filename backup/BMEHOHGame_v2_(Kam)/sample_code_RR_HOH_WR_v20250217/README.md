# Project Title: Hand of Hope - HOH v2.5
*An Exoskeleton Hand Robot that was designed to assist therapists to provide functional motor recovery of the hand grasping and opening movements following stroke.*

## Table of Contents
- [Introduction](#introduction)
- [Features](#features)
- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Communication Protocols](#communication-protocols)
- [Acknowledgement](#acknowledgement)
- [About Us](#about-us)

## Introduction
This project demonstrates how to control an exoskeleton hand robot using an ESP32 microcontroller. The exoskeleton hand is equipped with five linear actuators, allowing precise finger joint movements. The ESP32 is interfaced with an ICM20948 IMU sensor for motion tracking and features BLE communication for wireless control via a mobile app.

## Features
- **Control of Five Linear Actuators:** The ESP32 controls the linear actuators to perform tasks such as CPM (Continuous Passive Motion) movement, targeting specific angular positions, calibration, and reset.
- **Motion Tracking:** The ICM20948 IMU sensor provides real-time motion tracking capability to the exoskeleton hand.
- **Connectivity Detection:** The ESP32 detects cable and sensor connectivity issues.
- **Wireless Communication:** BLE module on ESP32 enables wireless communication with mobile devices for control and feedback.
- **Mobile App Interface:** An app user interface is available for users to control the exoskeleton hand robot and receive feedback.

## Hardware Requirements
- ESP32 Microcontroller
- Five Linear Actuators
- ICM20948 IMU Sensor
- Power Supply
- Necessary Cables and Connectors

## Software Requirements
- Arduino IDE or PlatformIO
- ESP32 Board Support Package
- ICM20948 Sensor Library
- BLE Library for ESP32
- Mobile App (iOS/Android) for controlling the exoskeleton hand

## Installation
1. **Set up the Development Environment:**
   - Install Arduino IDE or PlatformIO.
   - Add ESP32 support to the Arduino IDE or PlatformIO.

2. **Clone the Repository:**
   ```sh
   git clone https://github.com/o0fung/RR_HOH_BLE.git
   cd RR_HOH_BLE
   ```

3. **Upload the Firmware:**
   - Connect the ESP32 to your computer.
   - Open the project in Arduino IDE or PlatformIO.
   - Select the correct board and port.
   - Upload the firmware to the ESP32.

## Usage
1. **Power On:**
   - Connect the power supply to the ESP32 and linear actuators.
   - Power on the system.

2. **Calibration:**
   - Use the mobile app to calibrate the exoskeleton hand. Follow the on-screen instructions for calibration.

3. **Control Movements:**
   - Use the app to control the finger joint movements, set target positions, or perform CPM movements.

4. **Motion Tracking:**
   - The IMU sensor will provide real-time motion data to the ESP32, enabling precise tracking of hand movements.

5. **Connectivity Detection:**
   - The ESP32 will monitor the connectivity of cables and sensors, providing alerts in case of any issues.

## Communication Protocols
- **I2C Protocol:** Used for communication between ESP32 and ICM20948 IMU sensor.
- **BLE Protocol:** Used for wireless communication between ESP32 and mobile devices.

## Acknowledgement
This project is private and owned by Rehab-Robotics Company Limited, a subsidary company of Vincent Medical Holdings Limited. 

## About Us

### Vincent Medical Holdings Limited
Established in 1997, Vincent Medical Holdings Limited is a Hong Kong-headquartered medical device manufacturing group. We develop, manufacture and sell a wide range of medical devices to our customers around the globe, focusing on respiratory care, imaging disposable, and orthopaedic and rehabilitation products.

Our products include a range of electronic medical devices such as high-flow oxygen therapy devices, respiratory humidification systems, rehabilitation devices, as well as the related disposables in respiratory care and anesthesiology.

With our production base in Dongguan, China, along with the R&D and regulatory divisions in Dongguan Songshan Lake Technology Industrial Park, we are dedicated to bringing innovative, high-quality and reliable medical technologies and devices to the market.

### Our Mission and Values
***<u>Create Values for Better Lives</u>***

Here at Vincent Medical, everyone understands that in everything we do and what and how we do it, it will have a significant impact on patients’ safety and experience. Hence, it is our goal to ensure we are putting every effort to ensure that the patient gets the best quality possible from our products. The responsibility in delivering this promise is from everyone at Vincent Medical.

### Rehab-Robotics Company Limited
Rehab-Robotics is committed to advance technologies in the rehabilitation profession to help patients achieve maximum recovery outcomes. We are dedicated to provide an integration of robotics into your training activities of daily living, continuous education and professional support.

In partnership with the Hong Kong Polytechnic University and rehabilitation experts in Hong Kong, we have created, developed and promoted the fusion of cutting edge technology with advance muscle re-education concepts to improve motor recovery.

Our employees encompass a broad range of disciplines with expertise in biomechanics, electrical, mechanical and materials engineering, production, computer software development, quality control as well as experienced therapists, and business leaders that work closely as a team to accomplish the company vision.
