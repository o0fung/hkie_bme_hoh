import numpy
import collections

from Toolbox import of_Math
from scipy.signal import welch


BUFFER_SIZE_ICM = 200       # Window size for display ICM data in UI
BUFFER_SIZE_EMG = 5000      # Window size for display EMG data in UI
BUFFER_SIZE_RMS = 100       # Window size for computing EMG RMS

SAMPLE_FREQ_EMG = 1000      # Sampling frequency of EMG is 1000 Hz
SAMPLE_FREQ_ICM = 100       # Sampling frequency of ICM is 100 Hz
CUTOFF_ACC_LO = 3           # Filter for Accelerometer is low-pass 3 Hz
CUTOFF_GYR_HI = 1           # Filter for Gyroscope is high-pass 10 Hz
CUTOFF_MAG_LO = 5           # Filter for Magnetometer is low-pass 5 Hz

COMPLEMENTARY_FILTER_ALPHA = 0.98       # Weigh constant for complementary filter

LIST_OF_CHANNEL = ['acc', 'gyr', 'mag']     # Combinations for assembling ICM channel names
LIST_OF_AXE = ['X', 'Y', 'Z']

TO_RADIAN = numpy.pi / 180.0        # Multiplier for degree-radian conversion
TO_DEGREE = 180.0 / numpy.pi

WINDOW_SIZE_SMOOTH = 50             # Pulse detector optimization parameters
WINDOW_SIZE_THRESHOLD = 200
K = 1.0
REFRACTORY_PERIOD = 30
MAX_PULSE_WIDTH = 1000000
MIN_PULSE_WIDTH = 0
MAX_PULSE_WIDTH_CRITICAL = MAX_PULSE_WIDTH
MIN_PULSE_WIDTH_CRITICAL = MIN_PULSE_WIDTH
MAX_THRESHOLD = 180
MIN_THRESHOLD = -180
MAX_THRESHOLD_CRITCAL = MAX_THRESHOLD
MIN_THRESHOLD_CRITCAL = MIN_THRESHOLD
MIN_PEAK_LOC_CRITCAL = 0.0
MAX_PEAK_LOC_CRITCAL = 1.0


class Data:
    """
    Helper class object for working on both ICM and EMG data
    - Can accept bulk data at once or process data frame-by-frame
    - Can compute sensor orientation and analyse emg data
    """
    
    list_str_channel = {}
    # List of output data channels after signal processing
    # ICM and EMG data are stored separately and with different sampling rates.
    list_str_channel['icm'] = [
        'icmT',
        'accX',
        'accY',
        'accZ',
        'accT',
        'gyrX',
        'gyrY',
        'gyrZ',
        'gyrT',
        'magX',
        'magY',
        'magZ',
        'magT',
        'accX_',
        'accY_',
        'accZ_',
        'gyrX_',
        'gyrY_',
        'gyrZ_',
        'magX_',
        'magY_',
        'magZ_',
        'roll',
        'pitch',
        'yaw',
        'roll_',
        'pitch_',
        'yaw_',
    ]
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
        
        self.pulse_detect = []    # Pulse detection helper class object
        
    def set_pulse_detector(self, **kwargs):
        """
        Initialize the PulseDetector with specified parameters.
        
        Args:
            window_size_smooth (int): Window size for moving average smoothing.
            window_size_threshold (int): Window size for adaptive threshold calculation.
            k (float): Multiplier for std in adaptive threshold.
            min_pulse_width (int): Minimum number of samples for a valid pulse.
            refractory_period (int): Minimum number of samples between pulses.
            min_threshold (float): minimum threshold level for the dynamic threshold adjustment
        """
        self.pulse_detect.append(PulseDetector(**kwargs))
        
    def set_zero(self, n_icm=0, n_emg=0):
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
        self.ptr_icm_analysis = 0
        self.ptr_emg_analysis = 0

        # Reset the quaternion offset vector
        self.quat = of_Math.Quaternion(1, 0, 0, 0)
        self.quat_raw = of_Math.Quaternion(1, 0, 0, 0)
        self.quat_offset_inv = of_Math.Quaternion(1, 0, 0, 0)
        
        # Reset the rotation matrix
        self.rot = of_Math.Rotation()
        self.rot_raw = of_Math.Rotation()
        self.rot_offset = of_Math.Rotation()
        
        # Reset the Pulse Detector algorithm
        for i in range(len(self.pulse_detect)):
            if self.pulse_detect[i] is not None:
                self.pulse_detect[i].reset()
        
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
        self.buffer[dev].append(val)
    
    def load_data(self, icm, emg):
        # Only fill in data channel that is available in the data files
        
        # For ICM data
        length_icm = icm.shape[0]
        self.data_count['icm'] = length_icm
        for i in range(length_icm):
            for ch in icm.dtype.names:
                self.data['icm'][ch][i] = icm[ch][i]
                
        # For EMG data
        length_emg = emg.shape[0]
        self.data_count['emg'] = length_emg
        for i in range(length_emg):
            for ch in emg.dtype.names:
                self.data['emg'][ch][i] = emg[ch][i]
        
    def set_offset(self, is_reset=False):
        # Use current sensor orientation to compute the reference frame
        # Reference is represenated in quaternion and in rotation matrix
        
        if is_reset:
            # Reset the reference frame to identity
            self.quat_offset_inv = of_Math.Quaternion(1, 0, 0, 0)
            self.rot_offset = of_Math.Rotation()
            
        else:
            # Set the reference frame using current raw orientation
            self.quat_offset_inv = self.quat_raw.inv()
            self.rot_offset = of_Math.Rotation(matrix=self.rot_raw.matrix)
    
    def wrap_angles(self, a, a0):
        # Wrap angle reading if the angle shifted abruptly to out of range 180 degree
        if a - a0 > 180.0:
            a -= 360.0
        elif a - a0 < -180.0:
            a += 360.0
            
        return (a + 180.0) % 360.0 - 180.0
        
    def complementary_filter(self, a, a0, b, alpha, is_wrapped=True):
        # Complementary filter with option to wrap angles if needed
        
        if is_wrapped:
            # Wrap angle from accelerometer for exceeding +/- 180 degrees
            if b - a0 > 180:
                b -= 360
            elif b - a0 < -180:
                b += 360
        
        # Complementary filter
        out = alpha * a + (1 - alpha) * b
        
        # Wrap angle after complementary filter for exceeding +/- 180 degrees
        if is_wrapped:
            if out > 180:
                out -= 360
            elif out < -180:
                out += 360
            
        return out
    
    def track_euler_angles(self, x, x0, mode=None):
        # To fix Euler angles of X and Z axes for when the sensor is up-side-down
        # i.e. the Y axes is inverted and pointing toward ground
        
        if mode == 'continuous':
            # For when the sensor is flipped, the X and Z axes shifted 180 degrees
            if 90 < x - x0 < 270:
                x -= 180
            elif -270 < x - x0 < -90:
                x += 180
            
            return (x + 180) % 360 - 180
                
        if mode == 'unbound':
            # For when the sensor is flipped, the Y axes
            if x - x0 > 180:
                x -= 360 * ((numpy.abs(x - x0) - 180) // 360 + 1)
            elif x - x0 < -180:
                x += 360 * ((numpy.abs(x - x0) - 180) // 360 + 1)
                
            return x
            
        else:
            return (x + 180) % 360 - 180
    
    def compute_from_emg(self, dt):
        # Perform EMG analysis to output useful EMG features per data frame
        
        # Compute the root-mean-square
        rms = numpy.sqrt(numpy.mean(numpy.array(self.buffer['rms100']) ** 2))
        self.data['emg']['rms'][dt] = rms
        self.add_data_buffer('rms', rms)

        # Compute the power spectrum density from FFT of EMG
        frequencies, power_spectrum = welch(self.buffer['emg'], fs=1000)
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
    
    def compute_from_icm(self, dt, mode='euler'):
        # Compute orientation of the EMG sensor usign 9-dof IMU data
        
        if self.data['icm']['accT'][dt] and self.data['icm']['gyrT'][dt] and self.data['icm']['magT'][dt]:
            # All three ICM channels are available at this time instance dt
            # Can proceed to compute the Euler angle
            n = self.ptr_icm_analysis
            
            # Work frame by frame to fill up the ICM analysis results
            # User is supposed to fill in the raw 9-dof data somewhere else in the program
            # for data within a short time duration (dt)
            # Then this while loop do the data processing on the new raw 9-dof up to the latest sample at dt
            while n <= dt:
                
                if mode == 'euler':
                    # Use rotation motrix to compute Euler angles (preferred)
                    self.computation_euler_angle_per_frame(n)
                    
                elif mode == 'quaternion':
                    # Use quaternion to compute Euler angles (still having issues)
                    self.computation_quaternion_per_frame(n)
                
                for i in range(len(self.pulse_detect)):
                    if self.pulse_detect[i] is not None:
                        # Perform pulse detection to get repetitions in specified data channel
                        # Use data filtering, adaptive threshold with refractory period
                        
                        # Feed a sample of the specified data channel to the handler
                        self.pulse_detect[i].process_sample(
                            sample=self.data['icm']['pitch_'][n],
                            index=n, )
                    
                n += 1
            
            # Update the pointer for ICM analysis                
            self.ptr_icm_analysis = n
            
    def computation_euler_angle_per_frame(self, n):
        # Compute relative orientation of the EMG sensor using rotation matrix
        
        # Do Butterworth filter on 9-axis ICM data
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                # Get filtered data channel (low or high pass)
                self.data['icm'][f'{ch}{ax}_'][n] = self.filter[f'{ch}{ax}'].feed(self.data['icm'][f'{ch}{ax}'][n])
        
        # Do Normalization on accelerometer and magnetometer ICM data
        for ch in LIST_OF_CHANNEL:
            if ch in ['acc', 'mag']:
                x, y, z = self.data['icm'][f'{ch}X_'][n], self.data['icm'][f'{ch}Y_'][n], self.data['icm'][f'{ch}Z_'][n]
                magnitude = numpy.sqrt( x * x + y * y + z * z )
                
                # Get normalized 3D vector to unit
                self.data['icm'][f'{ch}X_'][n] = x / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Y_'][n] = y / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Z_'][n] = z / magnitude if magnitude > 0.1 else 0.0
        
        # Update the buffer for filtered & normalized 9-dof ICM data display
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                self.add_data_buffer(f'{ch}{ax}_', self.data['icm'][f'{ch}{ax}_'][n])
                
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
        self.data['icm']['roll'][n] = self.complementary_filter(self.data['icm']['roll'][n], self.data['icm']['roll'][n-1], roll_acc, COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        self.data['icm']['pitch'][n] = self.complementary_filter(self.data['icm']['pitch'][n], self.data['icm']['pitch'][n-1], pitch_acc, COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        self.data['icm']['yaw'][n] = self.complementary_filter(self.data['icm']['yaw'][n], self.data['icm']['yaw'][n-1], yaw_mag, alpha=COMPLEMENTARY_FILTER_ALPHA, is_wrapped=True)
        
        # Update the buffer for Euler angles in range of +/- 180 degree
        self.add_data_buffer('roll', self.data['icm']['roll'][n])
        self.add_data_buffer('pitch', self.data['icm']['pitch'][n])
        self.add_data_buffer('yaw', self.data['icm']['yaw'][n])
        
        # ======== Optional ============
        # USING ROTATION MATRIX for adjustment to Reference Frame
        # Convert Euler angles to rotation matrix
        # Compute rotation with respect to reference frame
        # self.rot_raw = of_Math.Rotation()
        # self.rot_raw.euler_to_matrix(roll=self.data['icm']['roll'][n] * TO_RADIAN,
        #                                 pitch=self.data['icm']['pitch'][n] * TO_RADIAN,
        #                                 yaw=self.data['icm']['yaw'][n] * TO_RADIAN, )
        # self.rot = self.rot_raw.relative_to(self.rot_offset)
        # # Compute relative Euler angles to reference frame
        # roll, pitch, yaw = self.rot.matrix_to_euler()
        
        # Resultant Euler angles is not in range of +/- 180 degree
        # Wrap the angles for better interpretation
        self.data['icm']['roll_'][n] = self.track_euler_angles(self.data['icm']['roll'][n], self.data['icm']['roll_'][n-1], mode='unbound')
        self.data['icm']['pitch_'][n] = self.track_euler_angles(self.data['icm']['pitch'][n], self.data['icm']['pitch_'][n-1], mode='unbound')
        self.data['icm']['yaw_'][n] = self.track_euler_angles(self.data['icm']['yaw'][n], self.data['icm']['yaw_'][n-1], mode='unbound')
        
        # Update the buffer for Euler angles with respect to the reference frame
        self.add_data_buffer('roll_', self.data['icm']['roll_'][n])
        self.add_data_buffer('pitch_', self.data['icm']['pitch_'][n])
        self.add_data_buffer('yaw_', self.data['icm']['yaw_'][n])
            
    def computation_quaternion_per_frame(self, n):
        # Compute relative orientation of the EMG sensor using quaternion
        # (Still not ready, having issue in quaternion, work in progress)
        
        # Do Butterworth filter on 9-axis ICM data
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                # Get filtered data channel (low or high pass)
                self.data['icm'][f'{ch}{ax}_'][n] = self.filter[f'{ch}{ax}'].feed(self.data['icm'][f'{ch}{ax}'][n])
        
        # Do Normalization on accelerometer and magnetometer ICM data
        for ch in LIST_OF_CHANNEL:
            if ch in ['acc', 'mag']:
                x, y, z = self.data['icm'][f'{ch}X_'][n], self.data['icm'][f'{ch}Y_'][n], self.data['icm'][f'{ch}Z_'][n]
                magnitude = numpy.sqrt( x * x + y * y + z * z )
                
                # Get normalized 3D vector to unit
                self.data['icm'][f'{ch}X_'][n] = x / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Y_'][n] = y / magnitude if magnitude > 0.1 else 0.0
                self.data['icm'][f'{ch}Z_'][n] = z / magnitude if magnitude > 0.1 else 0.0
        
        # Update the buffer for data display
        for ch in LIST_OF_CHANNEL:
            for ax in LIST_OF_AXE:
                self.add_data_buffer(f'{ch}{ax}_', self.data['icm'][f'{ch}{ax}_'][n])
                
        # Euler angle computation require at least two frames
        if n == 0:
            # Computation of angle from gyroscope data require readings from previous frame
            # Skip the first frame
            n += 1
            return
        
        # Get filtered and normalized ICM data
        ax, ay, az = self.data['icm']['accX_'][n], self.data['icm']['accY_'][n], self.data['icm']['accZ_'][n]
        gx, gy, gz = self.data['icm']['gyrX'][n], self.data['icm']['gyrY'][n], self.data['icm']['gyrZ'][n]
        mx, my, mz = self.data['icm']['magX_'][n], self.data['icm']['magY_'][n], self.data['icm']['magZ_'][n]
        
        # Get Euler angle from accelerometer
        # Use trigonometry (tan) to compute angles
        # Orientation: when looking at LED light and ON/OFF button pointing up
        roll_acc = numpy.arctan2(ax, -ay) * TO_DEGREE        # tilting side-to-side (Left -ve / Right +ve)
        pitch_acc = numpy.arctan2(-az, -ay) * TO_DEGREE      # tilting forward-backward (forward -ve / backward +ve)
        
        # Get Euler angle from magnetometer
        # Use Rotation Matrix (Euler X-Y-Z) to get the formula of magnetic field components from x- z- axes
        cos_roll = numpy.cos(roll_acc * TO_RADIAN)
        sin_roll = numpy.sin(roll_acc * TO_RADIAN)
        cos_pitch = numpy.cos(pitch_acc * TO_RADIAN)
        sin_pitch = numpy.sin(pitch_acc * TO_RADIAN)
        mag_in_x = mx * cos_roll - my * sin_roll * cos_pitch - mz * sin_roll * sin_pitch
        mag_in_z = mz * cos_pitch - my * sin_pitch
        
        # Use trigonometry (tan) to compute angles
        yaw_mag = numpy.arctan2(-mag_in_z, mag_in_x) * TO_DEGREE         # turning (anti-clockwise -ve / clockwise +ve)
        
        # Wrap angles when the angle shifts 180 degree
        self.data['icm']['roll'][n] = self.wrap_angles(roll_acc, self.data['icm']['roll'][n-1])
        self.data['icm']['pitch'][n] = self.wrap_angles(pitch_acc, self.data['icm']['pitch'][n-1])
        self.data['icm']['yaw'][n] = self.wrap_angles(yaw_mag, self.data['icm']['yaw'][n-1])
        
        self.add_data_buffer('roll', self.data['icm']['roll'][n])
        self.add_data_buffer('pitch', self.data['icm']['pitch'][n])
        self.add_data_buffer('yaw', self.data['icm']['yaw'][n])
        
        # USING QUATERNION ====================
        # Convert Euler angles from Acc and Mag to quaternion
        quat_acc_mag = of_Math.Quaternion()
        quat_acc_mag = quat_acc_mag.euler_to_quat(roll=roll_acc * TO_RADIAN, pitch=pitch_acc * TO_RADIAN, yaw=yaw_mag * TO_RADIAN)
        
        # Compute quaternion from time integration of gyroscope signal
        # addition of previous quaternion with derivative of quaternion
        quat_omega = of_Math.Quaternion(0, -gx * TO_RADIAN, gy * TO_RADIAN, -gz * TO_RADIAN)
        quat_dot = self.quat_raw * quat_omega
        quat_dot = quat_dot.scale(0.5)
        quat_gyr = self.quat_raw + quat_dot.scale(1/SAMPLE_FREQ_ICM)
        quat_gyr = quat_gyr.normalize()
        
        # Perform complementary filter with the quaternion from Acc and Mag signals
        # self.quat_raw = quat_gyr.complementary_filter(quat_acc_mag, alpha=COMPLEMENTARY_FILTER_ALPHA)
        # self.quat_raw = quat_gyr.complementary_filter(quat_acc_mag, alpha=0.0)
        self.quat_raw = quat_gyr.complementary_filter(quat_acc_mag, alpha=1.0)
        
        # Get the Euler angle representation for the raw quaternion
        # self.data['icm']['roll'][n], self.data['icm']['pitch'][n], self.data['icm']['yaw'][n] = self.quat_raw.quat_to_euler()
        # Update the buffer for plotting chart
        # self.add_data_buffer('roll', self.data['icm']['roll'][n])
        # self.add_data_buffer('pitch', self.data['icm']['pitch'][n])
        # self.add_data_buffer('yaw', self.data['icm']['yaw'][n])
        
        # Compute the Relative Rotation between Raw and Reference quaternion
        # Applying inverse of the reference quaternion, would first brings the system back to the reference orientation
        # Then applying raw quaternion brings it to the current orientationa
        self.quat = self.quat_offset_inv * self.quat_raw
        
        # Get the Euler angle representation for the raw quaternion with respect to the reference quaternion
        self.data['icm']['roll_'][n], self.data['icm']['pitch_'][n], self.data['icm']['yaw_'][n] = self.quat_raw.quat_to_euler()
        # Update the buffer for plotting chart
        self.add_data_buffer('roll_', self.data['icm']['roll_'][n])
        self.add_data_buffer('pitch_', self.data['icm']['pitch_'][n])
        self.add_data_buffer('yaw_', self.data['icm']['yaw_'][n])


class PulseDetector:
    def __init__(self, 
                 window_size_smooth=WINDOW_SIZE_SMOOTH, 
                 window_size_threshold=WINDOW_SIZE_THRESHOLD, 
                 k=K, 
                 refractory_period=REFRACTORY_PERIOD,
                 max_pulse_width=MAX_PULSE_WIDTH,
                 min_pulse_width=MIN_PULSE_WIDTH, 
                 max_pulse_width_critical=MAX_PULSE_WIDTH_CRITICAL,
                 min_pulse_width_critical=MIN_PULSE_WIDTH_CRITICAL, 
                 max_threshold=MAX_THRESHOLD,
                 min_threshold=MIN_THRESHOLD,
                 max_threshold_critical=MAX_THRESHOLD_CRITCAL,
                 min_threshold_critical=MIN_THRESHOLD_CRITCAL,
                 max_peak_loc_critical=MAX_PEAK_LOC_CRITCAL,
                 min_peak_loc_critical=MIN_PEAK_LOC_CRITCAL,
                 ):
        """
        Initialize the PulseDetector with specified parameters.
        
        Args:
            window_size_smooth (int): Window size for moving average smoothing.
            window_size_threshold (int): Window size for adaptive threshold calculation.
            k (float): Multiplier for std in adaptive threshold.
            min_pulse_width (int): Minimum number of samples for a valid pulse.
            refractory_period (int): Minimum number of samples between pulses.
        """
        self.smooth_window = of_Math.SlidingWindow(window_size_smooth)
        self.threshold_window = of_Math.SlidingWindow(window_size_threshold)
        self.k = k
        self.refractory_period = refractory_period
        self.max_pulse_width = max_pulse_width
        self.min_pulse_width = min_pulse_width
        self.max_threshold = max_threshold
        self.min_threshold = min_threshold
        self.max_pulse_width_critical = max_pulse_width_critical
        self.min_pulse_width_critical = min_pulse_width_critical
        self.max_threshold_critical = max_threshold_critical
        self.min_threshold_critical = min_threshold_critical
        self.max_peak_loc_critical = max_peak_loc_critical
        self.min_peak_loc_critical = min_peak_loc_critical
        
        # Initialize state variables
        self.in_pulse = False
        self.pulse_start = None
        self.last_pulse_end = -refractory_period  # Allow immediate first pulse
        
        self.current_pulse_samples = []     # List to temporarily store data samples of current pulse
        self.pulses = []                    # List to store detected pulses
        self.critical_pulses = []                     # List to store peaks for visualization or further analysis
        
        self.time = []                      # List to store timestamp of the data
        self.samples = []                   # List to store smoothed (filtered) data channel
        self.thresholds_min = []                # List to store adaptive thresholds
        self.thresholds_max = []                # List to store adaptive thresholds

    def process_sample(self, sample, index):
        """
        Process a single sample from the data stream.
        
        Args:
            sample (float): The current data sample.
            index (int): The index of the current sample.
        
        Returns:
            list of dict: Detected pulses in the current sample. Each dict contains 
                          'start', 'end', 'peak_index', 'peak_value'.
        """
        detected_pulses = []

        # Moving Average Filtering
        # Update smoothing window and get the smoothed value
        self.smooth_window.add_sample(sample)
        smoothed = self.smooth_window.get_mean()
        self.samples.append(smoothed)
        self.time.append(index)
        
        # Update threshold window and compute adaptive threshold
        self.threshold_window.add_sample(smoothed)
        # mean = self.threshold_window.get_mean()
        # std = self.threshold_window.get_std()
        # threshold = mean - self.k * std
        # threshold = max(threshold, self.min_threshold)
        self.thresholds_min.append(self.min_threshold)
        self.thresholds_max.append(self.max_threshold)
        
        # Pulse detection logic
        if not self.in_pulse:
            # Check if we can detect a new pulse
            #   Dynamic Threshold considered
            #   Refractory Period considered
            if self.min_threshold < smoothed < self.max_threshold and (index - self.last_pulse_end) >= self.refractory_period:
                # Start of a new pulse
                self.in_pulse = True
                self.pulse_start = index
                self.current_pulse_samples = [ (index, smoothed) ]  # List of tuples (index, value)
                
        else:
            # Inside a pulse; collect samples
            self.current_pulse_samples.append( (index, smoothed) )
            
            # Check if we can detect end of a pulse
            #   Dynamic Threshold considered
            #   Minimum Pulse Size considered
            if smoothed < self.min_threshold or smoothed > self.max_threshold:
                # Potential end of pulse
                pulse_end = index
                pulse_width = pulse_end - self.pulse_start
                
                if self.min_pulse_width <= pulse_width <= self.max_pulse_width:
                    # Valid pulse detected; find peak
                    # This peak info can help user to subsequently accept or reject a pulse
                    peak_max_index, peak_max_value, peak_min_index, peak_min_value = self.find_peak(self.current_pulse_samples)
                    peak_max_loc = (peak_max_index - self.pulse_start) / pulse_width
                    peak_min_loc = (peak_min_index - self.pulse_start) / pulse_width
                    pulse_info = {
                        'start': self.pulse_start,
                        'end': pulse_end,
                        'peak_max_index': peak_max_loc,
                        'peak_min_index': peak_min_loc,
                        'peak_max_value': peak_max_value,
                        'peak_min_value': peak_min_value,
                    }
                    detected_pulses.append(pulse_info)
                    self.pulses.append(pulse_info)
                    self.last_pulse_end = pulse_end
                    
                # Reset pulse state
                self.in_pulse = False
                self.pulse_start = None
                self.current_pulse_samples = []
                
        return detected_pulses

    def find_peak(self, pulse_samples):
        """
        Find the peak within the pulse samples.
        
        Args:
            pulse_samples (list of tuples): List containing (index, smoothed_value).
        
        Returns:
            tuple: (peak_index, peak_value)
        """
        if not pulse_samples:
            return (None, None, None, None)
        # Find the sample with maximum smoothed value
        peak_max = max(pulse_samples, key=lambda x: x[1])
        peak_min = min(pulse_samples, key=lambda x: x[1])
        return (peak_max[0], peak_max[1], peak_min[0], peak_min[1])

    def get_pulses(self):
        """
        Get all detected pulses.
        
        Returns:
            list of dict: List containing detected pulses.
        """
        return self.pulses
    
    def get_critical_pulses(self):
        self.critical_pulses = []
        
        for pulse in self.pulses:
            
            pulse_width = pulse['end'] - pulse['start']
            
            if pulse['peak_max_value'] > self.max_threshold_critical:
                continue
            
            if pulse['peak_min_value'] < self.min_threshold_critical:
                continue
            
            if pulse_width > self.max_pulse_width_critical:
                continue
            
            if pulse_width < self.min_pulse_width_critical:
                continue
            
            if pulse['peak_max_index'] > self.max_peak_loc_critical:
                continue
            
            if pulse['peak_min_index'] < self.min_peak_loc_critical:
                continue
            
            self.critical_pulses.append(pulse)
        
        return self.critical_pulses

    def reset(self):
        """
        Reset the detector's internal state.
        """
        self.in_pulse = False
        self.pulse_start = None
        self.last_pulse_end = -self.refractory_period
        self.current_pulse_samples = []
        self.pulses = []
        self.critical_pulses = []


class StepAnalyser:
    def __init__(self, data, pulses):
        self.data = data
        self.pulses = pulses
        self.event_start = []
        self.event_end = []
        
        for pulse in self.pulses:
            self.event_start.append(pulse['start'])
            self.event_end.append(pulse['end'])
        
    def get_step_peaks(self, dev, ch):
        output = []
        
        data = self.data[dev][ch]
        for pulse in self.pulses:
            samples = data[pulse['start'] : pulse['end']]
            output.append(max(samples))
            
        return output
