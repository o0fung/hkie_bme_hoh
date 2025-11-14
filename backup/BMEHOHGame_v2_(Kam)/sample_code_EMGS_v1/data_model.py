import os
import time
import numpy
import collections

from Toolbox import of_Math
from scipy.signal import welch


BUFFER_SIZE_ICM = 200       # Window size for display ICM data in UI
BUFFER_SIZE_EMG = 1000      # Window size for display EMG data in UI
BUFFER_SIZE_RMS = 100       # Window size for computing EMG RMS

SAMPLE_FREQ_EMG = 1000      # Sampling frequency of EMG is 1000 Hz
SAMPLE_FREQ_ICM = 100       # Sampling frequency of ICM is 100 Hz
CUTOFF_ACC_LO = 3           # Filter for Accelerometer is low-pass 3 Hz
CUTOFF_GYR_HI = 1           # Filter for Gyroscope is high-pass 10 Hz
CUTOFF_MAG_LO = 5           # Filter for Magnetometer is low-pass 5 Hz

COMPLEMENTARY_FILTER_ALPHA = 0.98       # Weigh constant for complementary filter

LIST_OF_CHANNEL = ['acc', 'gyr', 'mag']     # Combinations for assembling ICM channel names
LIST_OF_AXE = ['X', 'Y', 'Z']               # Combinations for assembling ICM channel names
LIST_OF_ANGLE = ['roll', 'pitch', 'yaw']    # Euler angle name

TO_RADIAN = numpy.pi / 180.0        # Multiplier for degree-radian conversion
TO_DEGREE = 180.0 / numpy.pi


class Data:
    """
    Helper class object for working on both ICM and EMG data
    - Can accept bulk data at once or process data frame-by-frame
    - Can compute sensor orientation and analyse emg data
    """
    
    """
    ===========================================
    Input
    - IMU Time in millisecond since data collection
        - icmT (in 1kHz) (reference)
        - accT, gyrT, magT (in 100Hz) (not in use)
    - 9 DOF IMU data for each frame
        - accX, accY, accZ (not in use)
        - gyrX, gyrY, gyrZ (not in use)
        - magX, magY, magZ (not in use)
    - Already Processed IMU features for each frame
        - accX_, accY_, accZ_ (required)
        - gyrX_, gyrY_, gyrZ_ (required)
        - magX_, magY_, magZ_ (required)
        - roll, pitch, yaw (not in use)
        - roll_, pitch_, yaw_  (required)
        
    - EMG Time in millisecond since data collection
        - emgT (in 1kHz)
    - EMG data for each frame
        - emg (not in use)
    - Processed EMG features for each frame
        - rms (required)
        - mnf (not in use)
        - mdf (not in use)
    ===========================================
    """
    
    list_str_channel = {}
    list_str_channel_normalized = []
    # List of output data channels after signal processing
    # ICM and EMG data are stored separately and with different sampling rates.
    list_str_channel['icm'] = ['icmT']
    
    for ch in LIST_OF_CHANNEL:
        list_str_channel['icm'].append(f'{ch}T')
        for ax in LIST_OF_AXE:
            list_str_channel['icm'].append(f'{ch}{ax}')
            
    for ang in LIST_OF_ANGLE:
        list_str_channel['icm'].append(f'{ang}')
        
    for ch in LIST_OF_CHANNEL:
        for ax in LIST_OF_AXE:
            list_str_channel_normalized.append(f'{ch}{ax}_')
            list_str_channel_normalized.append(f'{ch}{ax}_1')
            list_str_channel_normalized.append(f'{ch}{ax}_2')
    
    for ang in LIST_OF_ANGLE:
        list_str_channel_normalized.append(f'{ang}_')
        list_str_channel_normalized.append(f'{ang}_s')
        list_str_channel_normalized.append(f'{ang}_c')
        list_str_channel_normalized.append(f'{ang}_1')
        list_str_channel_normalized.append(f'{ang}_2')
        
    list_str_channel['icm'].extend(list_str_channel_normalized)   
    list_str_channel_normalized.append('label')
    
    list_str_channel['emg'] = [
        'emgT',
        'emg',
        'rms',
        'mnf',
        'mdf',
    ]
    
    def __init__(self):
        self.data = {}              # Store ICM and EMG data separately
        self.data_types = {}
        self.data_count = {}
        self.buffer = {}
        
    def set_zero(self, n_icm=0, n_emg=0):
        """
        Initialization of zero-padded Tensor
        """
        # Must be activated once at the start of each data acquisition session
        # Reset all data and handler to zero
        
        # Prepare a list of data type of ICM sensor
        self.data_types['icm'] = []
        for ch in self.list_str_channel['icm']:
            self.data_types['icm'].append((ch, 'f4'))
            
        # Prepare a list of data type of EMG sensor
        self.data_types['emg'] = []
        for ch in self.list_str_channel['emg']:
            self.data_types['emg'].append((ch, 'f4'))
        
        # Set zero data count for each sensor
        self.data_count['icm'] = n_icm
        self.data_count['emg'] = n_emg
        
        # Initiate empty structured array for each sensor
        self.data['icm'] = numpy.empty(n_icm, dtype=self.data_types['icm'])
        self.data['emg'] = numpy.empty(n_emg, dtype=self.data_types['emg'])
        
        # Initiate some deque buffers to store a short time window of the data
        # Deque buffer is a queue with fixed length, will pop first object when appending last object
        for dev in self.list_str_channel['icm']:
            # For ICM data
            self.buffer[dev] = collections.deque([0 for _ in range(BUFFER_SIZE_ICM)], maxlen=BUFFER_SIZE_ICM)
        for dev in self.list_str_channel['emg']:
            # For EMG data
            self.buffer[dev] = collections.deque([0 for _ in range(BUFFER_SIZE_EMG)], maxlen=BUFFER_SIZE_EMG)
        # For compute RMS of EMG data
        self.buffer['rms100'] = collections.deque([0 for _ in range(BUFFER_SIZE_RMS)], maxlen=BUFFER_SIZE_RMS)
        
        # Prepare Butterworth filters coefficients and buffers
        self.filter = {}
        #   For ICM data
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
                
        # Reset the pointer of ICM /EMG analysis
        # Keep track of where do we drop off in the varying filled ICM / EMG data array
        self.ptr_icm_analysis = 2
        self.ptr_emg_analysis = 2
        
    def add_zero(self, dev, length, missing_value=None):
        # Use only when the UI is receiving real-time data from sensor
        # The reserved memory size of the sensor data need to increase dynamically
        # Pad zeros to the reserved memory with defined length
        
        # An option to fill in the new array with predefined missing value
        if missing_value is None:
            missing_value = 0
            
        # Prepare an empty array filled with missing value
        new_extension = numpy.empty(length, dtype=self.data_types[dev])
        for ch in self.list_str_channel[dev]:
            new_extension[ch] = missing_value
        
        # Concatenate the prepared array to the main array
        # And update the data count
        self.data[dev] = numpy.concatenate((self.data[dev], new_extension))
        self.data_count[dev] += length
        
    def add_data_buffer(self, dev, val):
        """ For putting data into buffer """
        self.buffer[dev].append(val)
    
    def load_data(self, icm, emg):
        """
        Load IMU and EMG data from database
        """
        # Only fill in data channel that is available in the data files
        
        # For ICM data
        for i in range(self.data_count['icm']):
            for ch in icm.dtype.names:
                self.data['icm'][ch][i] = icm[ch][i]
                
        # For EMG data
        for i in range(self.data_count['emg']):
            for ch in emg.dtype.names:
                self.data['emg'][ch][i] = emg[ch][i]
    
    def save_data(self, path, suffix=''):
        """
        Save the output data to csv format
        """
        # Save all data to files for future use
        path_to_data = path
        
        # Create folder if not exists
        if not os.path.exists(path_to_data):
            os.mkdir(path_to_data)
        
        # Strip the end of the dataset for any zero pad
        self.data['icm'] = self.data['icm'][: numpy.nonzero(self.data['icm']['icmT'])[0][-1] + 1]
        
        # Fix the issue some row of data has no timestamp column
        for i in range(self.data['icm'].shape[0]):
            if self.data['icm']['icmT'][i] == 0:
                self.data['icm']['icmT'][i] = i * 10
                
        # Save ICM data as CSV file
        with open(os.path.join(path_to_data, f'icm_{suffix}.csv'), 'wb') as f:
            numpy.savetxt(f, self.data['icm'], delimiter=',', header=','.join(self.list_str_channel['icm']), fmt='%f'+',%f'*(len(self.list_str_channel['icm'])-1), comments='')
        
    def process_data(self):
        # Count the time becauase the process could be very long duration
        t0 = time.time()
        
        # Data processing start with index-2 because 2nd derivative is available by then
        for n in range(2, self.data_count['icm']):
            self.extract_features_from_icm(n)
            print(time.strftime(f"Time elapse: %H:%M:%S\tProgress: {n/self.data_count['icm']*100:1.1f} %% \tFrame Count: {n+1}\r", time.gmtime(time.time() - t0)), end='')
            
    def extract_features_from_icm(self, dt):
        """
        Compute features from the IMU sensor
        ===========================================
        Procedures
        - Filtering
        - Normalization
        - Compute Euler Angles
        """
        n = self.ptr_icm_analysis
        
        if self.data['icm']['accT'][dt] and self.data['icm']['gyrT'][dt] and self.data['icm']['magT'][dt]:
            
            # All three ICM channels are available at this time instance dt
            # Can proceed to compute the Euler angle
            
            # Work frame by frame to fill up the ICM analysis results
            # User is supposed to fill in the raw 9-dof data somewhere else in the program
            # for data within a short time duration (dt)
            # Then this while loop do the data processing on the new raw 9-dof up to the latest sample at dt
            while n <= dt:
                
                self.filtering_imu(n)
                self.normalize_acc_mag(n, ch_in='_', ch_out='_')
                
                self.computation_euler_angle(n)
                self.convert_euler_angle_to_sin_cos(n)
                
                self.compute_derivative(n, '_', '_1')
                self.compute_derivative(n, '_1', '_2')
                
                # Update the buffer for filtered & normalized 9-dof ICM data display
                for ch in LIST_OF_CHANNEL:
                    for ax in LIST_OF_AXE:
                        self.add_data_buffer(f'{ch}{ax}_', self.data['icm'][f'{ch}{ax}_'][n])
                        
                for ang in LIST_OF_ANGLE:
                    self.add_data_buffer(f'{ang}', self.data['icm'][f'{ang}'][n])
                    self.add_data_buffer(f'{ang}_', self.data['icm'][f'{ang}_'][n])
                
                n += 1
            
            # Update the pointer for ICM analysis                
            self.ptr_icm_analysis = n
            
    def filtering_imu(self, n):
        
        # Do Butterworth filter on 9-axis ICM data
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                # Get filtered data channel (low or high pass)
                self.data['icm'][f'{ch}{ax}_'][n] = self.filter[f'{ch}{ax}'].feed(self.data['icm'][f'{ch}{ax}'][n])
        
    def normalize_acc_mag(self, n, ch_in='', ch_out=''):
        for ch in LIST_OF_CHANNEL:
            # Do Normalization on accelerometer and magnetometer ICM data
            if ch in ['acc', 'mag']:
                x, y, z = self.data['icm'][f'{ch}X{ch_in}'][n], self.data['icm'][f'{ch}Y{ch_in}'][n], self.data['icm'][f'{ch}Z{ch_in}'][n]
                magnitude = numpy.sqrt( x * x + y * y + z * z )
                
                # Get normalized 3D vector to unit
                self.data['icm'][f'{ch}X{ch_out}'][n] = x / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Y{ch_out}'][n] = y / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Z{ch_out}'][n] = z / magnitude if magnitude > 0.1 else 0.0
                
            # Do Normalization on gyroscope ICM data
            # if ch in ['gyr']:
            #     x, y, z = self.data['icm'][f'{ch}X{ch_in}'][n], self.data['icm'][f'{ch}Y{ch_in}'][n], self.data['icm'][f'{ch}Z{ch_in}'][n]
                
            #     self.data['icm'][f'{ch}X{ch_out}'][n] = x / 250.0 if -250.0 < x < 250.0 else numpy.sign(x)
            #     self.data['icm'][f'{ch}Y{ch_out}'][n] = y / 250.0 if -250.0 < y < 250.0 else numpy.sign(y)
            #     self.data['icm'][f'{ch}Z{ch_out}'][n] = z / 250.0 if -250.0 < z < 250.0 else numpy.sign(z)
    
    def computation_euler_angle(self, n):
        if n == 0:
            # Computation of angle from gyroscope data require readings from previous frame
            # Skip the first frame
            n += 1
            return
        
        # Get a sample of filtered and normalized ICM data
        ax, ay, az = self.data['icm']['accX_'][n], self.data['icm']['accY_'][n], self.data['icm']['accZ_'][n]
        gx, gy, gz = self.data['icm']['gyrX'][n], self.data['icm']['gyrY'][n], self.data['icm']['gyrZ'][n]
        mx, my, mz = self.data['icm']['magX_'][n], self.data['icm']['magY_'][n], self.data['icm']['magZ_'][n]
        
        # Get Euler angle from accelerometer
        # Use trigonometry (arctan2) to compute angles (output should be in range +/- 180 degree)
        # Orientation: when looking at sensor LED light and ON/OFF button pointing up
        roll_acc = numpy.arctan2(ax, -ay) * TO_DEGREE        # tilting side-to-side (Left -ve / Right +ve)
        pitch_acc = numpy.arctan2(-az, -ay) * TO_DEGREE      # tilting forward-backward (forward -ve / backward +ve)
        
        # Get Euler angle from gyroscope
        # Use time integration of angles
        # Orientation: when looking at sensor LED light and ON/OFF button pointing up
        self.data['icm']['roll'][n] = self.data['icm']['roll'][n-1] - gz / SAMPLE_FREQ_ICM      # tilting side-to-side (Left -ve / Right +ve)
        self.data['icm']['pitch'][n] = self.data['icm']['pitch'][n-1] - gx / SAMPLE_FREQ_ICM    # tilting forward-backward (forward -ve / backward +ve)
        self.data['icm']['yaw'][n] = self.data['icm']['yaw'][n-1] + gy / SAMPLE_FREQ_ICM        # turning (anti-clockwise -ve / clockwise +ve)
        
        # Get Euler angle from magnetometer
        # Use Rotation Matrix (Euler X-Y-Z) to get the formula of magnetic field components from x- z- axes
        cos_roll = numpy.cos(self.data['icm']['roll'][n] * TO_RADIAN)
        sin_roll = numpy.sin(self.data['icm']['roll'][n] * TO_RADIAN)
        cos_pitch = numpy.cos(self.data['icm']['pitch'][n] * TO_RADIAN)
        sin_pitch = numpy.sin(self.data['icm']['pitch'][n] * TO_RADIAN)
        mag_in_x = mx * cos_roll - my * sin_roll * cos_pitch - mz * sin_roll * sin_pitch
        mag_in_z = mz * cos_pitch - my * sin_pitch
        
        # Use trigonometry (arctan) to compute angles (output should be in range +/- 180 degree)
        yaw_mag = numpy.arctan2(-mag_in_z, mag_in_x) * TO_DEGREE         # turning (anti-clockwise -ve / clockwise +ve)
        
        # Complementary Filter to get Euler angles with sensor fusion
        # Merge the angle readings from both accelerometer/magnetometer and gyroscope with a defined weight
        roll = self.complementary_filter(self.data['icm']['roll'][n], self.data['icm']['roll'][n-1], roll_acc, COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        pitch = self.complementary_filter(self.data['icm']['pitch'][n], self.data['icm']['pitch'][n-1], pitch_acc, COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        yaw = self.complementary_filter(self.data['icm']['yaw'][n], self.data['icm']['yaw'][n-1], yaw_mag, alpha=COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        
        self.data['icm']['roll'][n] = roll
        self.data['icm']['pitch'][n] = pitch
        self.data['icm']['yaw'][n] = yaw
        
        self.data['icm']['roll_'][n] = roll
        self.data['icm']['pitch_'][n] = pitch
        self.data['icm']['yaw_'][n] = yaw
        
        return (roll, pitch, yaw)
        
    def convert_euler_angle_to_sin_cos(self, n):
        """
        Represent angles using sine and cosine:
          Because of periodicity, directly standardizing angles  can be problematic because angles wrap around
          For instance, +180 deg and -180 deg represent the same orientation, but standarization would treat them as 
          distant points, introducing artificial discontinuity
          
          By converting the angle into its sine and cosine components, it preserves the periodicity and eliminate
          the discontinuity at the wrap-around point.       
        """
        
        self.data['icm']['roll_s'][n] = numpy.sin(self.data['icm']['roll'][n] * TO_RADIAN)
        self.data['icm']['roll_c'][n] = numpy.cos(self.data['icm']['roll'][n] * TO_RADIAN)
        
        self.data['icm']['pitch_s'][n] = numpy.sin(self.data['icm']['pitch'][n] * TO_RADIAN)
        self.data['icm']['pitch_c'][n] = numpy.cos(self.data['icm']['pitch'][n] * TO_RADIAN)
        
        self.data['icm']['yaw_s'][n] = numpy.sin(self.data['icm']['yaw'][n] * TO_RADIAN)
        self.data['icm']['yaw_c'][n] = numpy.cos(self.data['icm']['yaw'][n] * TO_RADIAN)
    
    def compute_derivative(self, n, ch_in='_', ch_out='_1'):
        """ Compute derivatives of the data channels """
        for channel in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                ch = f'{channel}{ax}'
                self.data['icm'][f'{ch}{ch_out}'][n] = self.data['icm'][f'{ch}{ch_in}'][n] - self.data['icm'][f'{ch}{ch_in}'][n-1]
    
        """ Compute derivatives for the angles """
        for ch in LIST_OF_ANGLE:
            self.data['icm'][f'{ch}{ch_out}'][n] = self.data['icm'][f'{ch}{ch_in}'][n] - self.data['icm'][f'{ch}{ch_in}'][n-1]
    
    def extract_features_from_emg(self, dt):
        """
        Compute features from the EMG sensor
        ===========================================
        Procedures
        - Filtering
        - Normalization
        - Compute Euler Angles
        """
        # Perform EMG analysis to output useful EMG features per data frame
        
        # Compute the root-mean-square
        rms = numpy.sqrt(numpy.mean(numpy.array(self.buffer['rms100']) ** 2))
        self.data['emg']['rms'][dt] = rms
        self.add_data_buffer('rms', rms)

        # Compute the power spectrum density from FFT of EMG
        frequencies, power_spectrum = welch(numpy.array(self.buffer['emg']), fs=1000)
        if not power_spectrum.all():
            return [0], [0]
                
        # Compute the MNF of the EMG
        mean_frequency = numpy.sum(power_spectrum * frequencies) / numpy.sum(power_spectrum)
        self.data['emg']['mnf'][dt] = mean_frequency
        
        # Compute the MDF of the EMG
        cumulative_power = numpy.cumsum(power_spectrum)     # cumulative sum of the power spectrum
        total_power = cumulative_power[-1]
        median_freq_index = numpy.where(cumulative_power >= total_power / 2)[0][0]
        median_frequency = frequencies[median_freq_index]   # median frequency
        self.data['emg']['mdf'][dt] = median_frequency
            
        return frequencies, power_spectrum
    
    def complementary_filter(self, a, a0, b, alpha, is_wrapped=True):
        """
        Complementary Filter
         and considered discontinuous data by wrapping up the results
        """
        # Complementary filter with option to wrap angles if needed
        
        if is_wrapped:
            # Wrap angle from first source for exceeding +/- 180 degrees
            if b - a0 > 180:
                b -= 360
            elif b - a0 < -180:
                b += 360
        
        # Complementary filter
        out = alpha * a + (1 - alpha) * b
        
        # Wrap angle of the output after complementary filter for exceeding +/- 180 degrees
        if is_wrapped:
            if out > 180:
                out -= 360
            elif out < -180:
                out += 360
            
        return out
    