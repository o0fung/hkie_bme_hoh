import argparse
import traceback
import numpy
import pywt
import os

import run

from matplotlib import pyplot
from Toolbox import of_Math


SAMPLE_FREQ_ICM = 100       # Sampling frequency is 100 Hz
CUTOFF_ACC_LO = 3           # Accelerometer is low-pass 3 Hz
CUTOFF_GYR_HI = 10          # Gyroscope is high-pass 10 Hz
CUTOFF_MAG_LO = 5           # Magnetometer is low-pass 5 Hz
COMPLEMENTARY_FILTER_ALPHA = 0.98
LIST_OF_CHANNEL = ['acc', 'gyr', 'mag']
LIST_OF_AXE = ['X', 'Y', 'Z']


class Dataset(run.Operation):
    def __init__(self, data, skip_filter=False):
        super().__init__(data, skip_filter)
    
    def setup_output(self):
        self.output = {}
        
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                # Filtered channels
                self.output[f'{ch}{ax}'] = numpy.zeros(self.icm[f'{ch}{ax}'].shape)
                
                if ch in ['acc', 'mag']:
                    # Normalized channels (acc & mag only)
                    self.output[f'{ch}{ax}u'] = numpy.zeros(self.icm[f'{ch}{ax}'].shape)
                    
        # Roll angle (Phi)
        self.output['phi'] = numpy.zeros(self.icm['icmT'].shape)
        self.output['roll'] = numpy.zeros(self.icm['icmT'].shape)
        # Pitch angle (theta)
        self.output['theta'] = numpy.zeros(self.icm['icmT'].shape)
        self.output['pitch'] = numpy.zeros(self.icm['icmT'].shape)
        # Yaw angle (psi)
        self.output['psi'] = numpy.zeros(self.icm['icmT'].shape)
        self.output['yaw'] = numpy.zeros(self.icm['icmT'].shape)
                
    def setup_filtering(self):
        self.filter = {}
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                
                if ch == 'acc':
                    co = CUTOFF_ACC_LO
                    mo = 'low'
                    
                if ch == 'gyr':
                    co = CUTOFF_GYR_HI
                    mo = 'high'
                    
                if ch == 'mag':
                    co = CUTOFF_MAG_LO
                    mo = 'low'
                    
                self.filter[f'{ch}{ax}'] = of_Math.Butterworth()
                self.filter[f'{ch}{ax}'].butter(sample_freq=SAMPLE_FREQ_ICM, cutoff=co, mode=mo)
        
    def do_filter(self, n):
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                # Get filtered data channel (low or high pass)
                self.output[f'{ch}{ax}'][n] = self.filter[f'{ch}{ax}'].feed(self.icm[f'{ch}{ax}'][n])
                
    def do_normalize(self, n):
        for ch in LIST_OF_CHANNEL:
            if ch in ['acc', 'mag']:
                x, y, z = self.output[f'{ch}X'][n], self.output[f'{ch}Y'][n], self.output[f'{ch}Z'][n]
                magnitude = numpy.sqrt( x * x + y * y + z * z )
                
                if magnitude > 0.1:
                    # Get normalized 3D vector to unit
                    self.output[f'{ch}Xu'][n] = x / magnitude
                    self.output[f'{ch}Yu'][n] = y / magnitude
                    self.output[f'{ch}Zu'][n] = z / magnitude
                else:
                    # Handle zero magnitude to avoid division by zero
                    self.output[f'{ch}Xu'][n] = 0.0
                    self.output[f'{ch}Yu'][n] = 0.0
                    self.output[f'{ch}Zu'][n] = 0.0
                    
    def do_quaternion(self, n):
        omega = of_Math.Quaternion()
        omega = numpy.array([0.0, self.output['gyrX'][n], self.output['gyrY'][n], self.output['gyrZ'][n]])
                    
    def get_euler_angle_from_icm(self, n, alpha=COMPLEMENTARY_FILTER_ALPHA):
        if n == 0:
            # Computation of angle from gyroscope data require readings from previous frame
            # Skip the first frame
            return
        
        # Get filtered and normalized ICM data
        ax, ay, az = self.output['accXu'][n], self.output['accYu'][n], self.output['accZu'][n]
        gx, gy, gz = self.output['gyrX'][n], self.output['gyrY'][n], self.output['gyrZ'][n]
        mx, my, mz = self.output['magXu'][n], self.output['magYu'][n], self.output['magZu'][n]
        
        # Get Euler angle from accelerometer
        phi_acc = numpy.arctan2(ay, az)
        theta_acc = numpy.arctan2(-ax, numpy.sqrt(ay * ay + az * az))
        
        # Get Euler angle from gyroscope
        self.output['phi'][n] = self.output['phi'][n-1] + gx / SAMPLE_FREQ_ICM
        self.output['theta'][n] = self.output['theta'][n-1] + gy / SAMPLE_FREQ_ICM
        self.output['psi'][n] = self.output['psi'][n-1] + gz / SAMPLE_FREQ_ICM
        
        # Get Euler angle from magnetometer
        cos_phi = numpy.cos(self.output['phi'][n])
        sin_phi = numpy.sin(self.output['phi'][n])
        cos_theta = numpy.cos(self.output['theta'][n])
        sin_theta = numpy.sin(self.output['theta'][n])
        phi_mag = mx * cos_theta + mz * sin_theta
        theta_mag = mx * sin_phi * sin_theta + my * cos_phi - mz * sin_phi * cos_theta
        yaw_mag = numpy.arctan2(-theta_mag, phi_mag)
        
        # Complementary Filter to get Euler angles with sensor fusion
        self.output['phi'][n] = alpha * self.output['phi'][n] + (1 - alpha) * phi_acc
        self.output['theta'][n] = alpha * self.output['theta'][n] + (1 - alpha) * theta_acc
        self.output['psi'][n] = alpha * self.output['psi'][n] + (1 - alpha) * yaw_mag
        # Convert from Radian to Degree
        self.output['roll'][n] = self.output['phi'][n] / numpy.pi * 180.0
        self.output['pitch'][n] = self.output['theta'][n] / numpy.pi * 180.0
        self.output['yaw'][n] = self.output['psi'][n] / numpy.pi * 180.0
        
    def work(self, calibrate_at_n=None):
        length = self.icm.shape[0]      # Length of ICM data
        
        self.setup_output()             # Setup work
        self.setup_filtering()
        
        for n in range(length):         # Loop for each frame
            self.do_filter(n)           # Data processing
            self.do_normalize(n)
            
            self.get_euler_angle_from_icm(n)
            
    def display(self, start=0, end=None, period=None):
        # Configure the time range of frequency map
        if end is None:        
            if period is None:
                end = int(self.icm['icmT'][-1])
            else:
                end = int(start + period)
        
        pyplot.figure('Output', figsize=(12, 8))
        
        ax = pyplot.subplot(4, 1, 1)
        pyplot.plot(data.icm['icmT'][start:end], data.output['accXu'], label='accX')
        pyplot.plot(data.icm['icmT'][start:end], data.output['accYu'], label='accY')
        pyplot.plot(data.icm['icmT'][start:end], data.output['accZu'], label='accZ')
        pyplot.legend()
        
        pyplot.subplot(4, 1, 2, sharex=ax)
        pyplot.plot(data.icm['icmT'][start:end], data.output['gyrX'], label='gyrX')
        pyplot.plot(data.icm['icmT'][start:end], data.output['gyrY'], label='gyrY')
        pyplot.plot(data.icm['icmT'][start:end], data.output['gyrZ'], label='gyrZ')
        pyplot.legend()
        
        pyplot.subplot(4, 1, 3, sharex=ax)
        pyplot.plot(data.icm['icmT'][start:end], data.output['magXu'], label='magX')
        pyplot.plot(data.icm['icmT'][start:end], data.output['magYu'], label='magY')
        pyplot.plot(data.icm['icmT'][start:end], data.output['magZu'], label='magZ')
        pyplot.legend()
        
        pyplot.subplot(4, 1, 4, sharex=ax)
        pyplot.plot(data.icm['icmT'][start:end], data.output['roll'], label='roll')
        pyplot.plot(data.icm['icmT'][start:end], data.output['pitch'], label='pitch')
        pyplot.plot(data.icm['icmT'][start:end], data.output['yaw'], label='yaw')
        pyplot.legend()
        
        pyplot.show()

if __name__ == '__main__':
    # parse from command line the target data directory path
    parser = argparse.ArgumentParser(description='Run and test the algorithm')
    parser.add_argument('path', help='target directory path to data')
    args = vars(parser.parse_args())
    
    print(f'>> Run and test algorithm')
    print(f'>> Data path: {args["path"]}')
    print(f'>> Data loading successful.')
    
    buffer = {'icm': None, 'emg': None}

    # Load ICM data
    with open(os.path.join(args['path'], 'icm.data'), 'rb') as f:
        buffer['icm'] = numpy.load(f, allow_pickle=True)
        
    # Load EMG data
    with open(os.path.join(args['path'], 'emg.data'), 'rb') as f:
        buffer['emg'] = numpy.load(f, allow_pickle=True)
    
    # Run the data algorithm
    data = Dataset(buffer, skip_filter=True)
    data.set_path(args['path'])
    
    data.work()

    data.display()
    