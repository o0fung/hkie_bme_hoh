import numpy
import collections


def map(x, x_min, x_max, is_bound=True):
    x = numpy.asarray(x)                        # Convert input to a numpy array
    output = (x - x_min) / (x_max - x_min)      # normalize to the range: min and max
    if is_bound:                                # decide if the output bound to the range
        output[x >= x_max] = 1.0
        output[x <= x_min] = 0.0
    
    # convert the result back to its original type: float or list 
    return output.tolist() if isinstance(x, numpy.ndarray) else float(output)


def nearest(array, val):
    # get the index of array that has value closest to val
    array = numpy.asarray(array)
    return (numpy.abs(array - val)).argmin()
    
    
def get_fourier(array, rate):
    # get the fourier transform plot (x-y axes)
    n = len(array)
    fft = numpy.fft.fft(numpy.asarray(array))[1:n//2]
    freq = numpy.fft.fftfreq(n, 1/rate)[1:n//2]
    energy = numpy.abs(fft) ** 2
    
    return freq, energy


def sigmoid(x):
    return 1. / (1 + numpy.exp(-x))


def sigmoid_derivative(values):
    return values * (1 - values)


def tanh_derivative(values):
    return 1. - values ** 2


def rand_arr(a, b, *args):
    # create uniform random array with values in [a, b) and shaped in args
    return numpy.random.rand(*args) * (b - a) + a


class Butterworth:
    FILTER_BUFFER_SIZE = 3
    
    def __init__(self):
        # Setup buffer
        self.buffer_in = collections.deque(numpy.zeros(self.FILTER_BUFFER_SIZE), maxlen=self.FILTER_BUFFER_SIZE)
        self.buffer_out = collections.deque(numpy.zeros(self.FILTER_BUFFER_SIZE), maxlen=self.FILTER_BUFFER_SIZE)
        # Setup coefficients
        self.a = numpy.zeros(self.FILTER_BUFFER_SIZE)
        self.b = numpy.zeros(self.FILTER_BUFFER_SIZE)
        
        self.set_enable(True)
        
    def set_enable(self, val):
        if type(val) is bool:
            self.enable = val

    def butter(self, sample_freq, cutoff=None, mode='low'):
            
        # polynomial coefficient of 2nd order Butterworth filter
        ita = 1.0 / numpy.tan(numpy.pi * cutoff / sample_freq)
        q = numpy.sqrt(2.0)
        self.b[0] = 1.0 / (1.0 + q * ita + ita * ita)
        self.b[1] = self.b[0] * 2
        self.b[2] = self.b[0]
        self.a[1] = 2.0 * (ita * ita - 1.0) * self.b[0]
        self.a[2] = -(1.0 - q * ita + ita * ita) * self.b[0]
        
        if mode == 'high':
            self.b[0] = self.b[0] * ita * ita
            self.b[1] = self.b[1] * ita * ita * -1
            self.b[2] = self.b[2] * ita * ita
        
        return self.a, self.b
    
    def feed(self, data_in):
        if self.enable:
            
            # Register and shift data into buffer array
            self.buffer_in.appendleft(data_in)
            self.buffer_out.appendleft(0.0)
            
            # Compute filtered data using 2nd order Butterworth Filter
            for i in range(3):
                self.buffer_out[0] += self.b[i] * self.buffer_in[i]
                self.buffer_out[0] += self.a[i] * self.buffer_out[i]
        
            # Filtered
            return self.buffer_out[0]
        
        else:
            return None
        
    def filt(self, data):
        if self.enable:
            
            # Prepare filter output data array
            output = numpy.zeros(data.shape)
            
            # Feed input data into filter and put output to data array
            for i in range(len(data)):
                output[i] = self.feed(data[i])
                
            return output
        
        else:
            return None
        

class Quaternion:
    def __init__(self, w=None, x=None, y=None, z=None):
        if w is None or x is None or y is None or z is None:
            return
        
        self.set_vector(w, x, y, z)

    def set_vector(self, w, x, y, z):
        self.w = w
        self.x = x
        self.y = y
        self.z = z
        self.vector = numpy.array([w, x, y, z])
        
    def __mul__(self, quat):
        w = self.w * quat.w - self.x * quat.x - self.y * quat.y - self.z * quat.z
        x = self.w * quat.x + self.x * quat.w + self.y * quat.z - self.z * quat.y
        y = self.w * quat.y - self.x * quat.z + self.y * quat.w + self.z * quat.x
        z = self.w * quat.z + self.x * quat.y - self.y * quat.x + self.z * quat.w
        return Quaternion(w, x, y, z)
    
    def __add__(self, quat):
        w = self.w + quat.w
        x = self.x + quat.x
        y = self.y + quat.y
        z = self.z + quat.z
        return Quaternion(w, x, y, z)
    
    def scale(self, scalar):
        w = self.w * scalar
        x = self.x * scalar
        y = self.y * scalar
        z = self.z * scalar
        return Quaternion(w, x, y, z)
    
    def norm(self):
        # Get magnitude of the quaternion
        # Equivalent to squared norm: i.e. q* dot q
        return numpy.sqrt(self.w ** 2 + self.x ** 2 + self.y ** 2 + self.z ** 2)
    
    def normalize(self):
        # Get unit quaternion
        n = self.norm()
        w = self.w / n
        x = self.x / n
        y = self.y / n
        z = self.z / n
        
        if n == 0:
            return Quaternion(1, 0, 0, 0)
        else:
            return Quaternion(w, x, y, z)
    
    def inv(self):
        # Inverse of the quaternion
        # For unit quaternion, inverse is equal to conjugate
        w = self.w
        x = -self.x
        y = -self.y
        z = -self.z
        return Quaternion(w, x, y, z)
    
    def dot(self, quat):
        # Dot product of two quaternion
        return self.w * quat.w + self.x * quat.x + self.y * quat.y + self.z * quat.z
    
    def complementary_filter(self, quat, alpha):
        w = alpha * self.w + (1 - alpha) * quat.w
        x = alpha * self.x + (1 - alpha) * quat.x
        y = alpha * self.y + (1 - alpha) * quat.y
        z = alpha * self.z + (1 - alpha) * quat.z
        
        return Quaternion(w, x, y, z).normalize()
    
    def euler_to_quat(self, roll, pitch, yaw):
        # Convert angles to radians
        # [roll, pitch, yaw] -> [w, x, y, z]
        
        cy = numpy.cos(yaw * 0.5)
        sy = numpy.sin(yaw * 0.5)
        cp = numpy.cos(pitch * 0.5)
        sp = numpy.sin(pitch * 0.5)
        cr = numpy.cos(roll * 0.5)
        sr = numpy.sin(roll * 0.5)
        
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        
        self.set_vector(w, x, y, z)
        
        return self.normalize()
    
    def quat_from_axis_angle(self, angle):
        # Convert a rotation defined by an axis and angle into a quaternion
        # (angle in radians)
        cos = numpy.cos(angle / 2)
        sin = numpy.sin(angle / 2)
        return Quaternion(cos, self.x * sin, self.y * sin, self.z * sin)
    
    def quat_from_rot_matrix(self, R):
        # Validate the rotation matrix R is 3x3
        # Please ensure the rotation matrix R is orthogonal
        #  and has a determinant of +1 before converting
        if not R.shape == (3, 3):
            return
        
        r11, r12, r13 = R[0][0], R[0][1], R[0][2]
        r21, r22, r23 = R[1][0], R[1][1], R[1][2]
        r31, r32, r33 = R[2][0], R[2][1], R[2][2]
        
        tr = r11 + r22 + r33
        
        if tr > 0:
            s = numpy.sqrt(1.0 + tr) * 2
            w = s / 4
            x = (r32 - r23) / s
            y = (r13 - r31) / s
            z = (r21 - r12) / s
            
        elif r11 > r22 and r11 > r33:
            s = numpy.sqrt(1.0 + r11 - r22 - r33) * 2
            w = (r32 - r23) / s
            x = s / 4
            y = (r12 + r21) / s
            z = (r13 + r31) / s
            
        elif r22 > r33:
            s = numpy.sqrt(1.0 + r22 - r11 - r33) * 2
            w = (r13 - r31) / s
            x = (r12 + r21) / s
            y = s / 4
            z = (r23 + r32) / s    
            
        else:
            s = numpy.sqrt(1.0 + r33 - r11 - r22) * 2
            w = (r21 - r12) / s
            x = (r13 + r31) / s
            y = (r23 + r32) / s
            z = s / 4
            
        return Quaternion(w, x, y, z)
        
    def quat_to_euler(self):
        # Convert quaternion to euler angles (roll, pitch, yaw)
        # [w, x, y, z] -> [roll, pitch, yaw]
        w, x, y, z = self.vector
        
        # Roll (x-axis rotation)
        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x**2 + y**2)
        roll = numpy.arctan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2.0 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = numpy.sign(sinp) * (numpy.pi / 2)  # use 90 degrees if out of range
        else:
            pitch = numpy.arcsin(sinp)

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y**2 + z**2)
        yaw = numpy.arctan2(siny_cosp, cosy_cosp)
        
        return (roll / numpy.pi * 180.0, pitch / numpy.pi * 180.0, yaw / numpy.pi * 180.0)
    
    def relative_angle(self, quat):
        # Angle between two quaternion
        rel = quat.inv() * self
        return 2 * numpy.arctan2(numpy.linalg.norm(rel.vector[1:4]), rel.vector[0]) / numpy.pi * 180.0
    
    def rotate(self, vector):
        # Rotate a 3D vector using the quaternion
        # Return with the updated 3D vector
        q_v = Quaternion(0, vector[0], vector[1], vector[2])
        q_conj = self.inv()
        q_rot = self * q_v * q_conj
        return q_rot.vector[1:]
    
    
class Rotation:
    def __init__(self, matrix=None):
        if matrix is not None:
            self.matrix = matrix
        else:
            self.identity()
            
    def __mul__(self, rotation):
        matrix = self.matrix @ rotation.matrix
        return Rotation(matrix)
    
    def identity(self):
        self.matrix = numpy.array([[1, 0, 0],
                                   [0, 1, 0],
                                   [0, 0, 1]])
    
    def relative_to(self, reference):
        matrix = reference.matrix.T @ self.matrix
        return Rotation(matrix)
    
    def euler_to_matrix(self, roll, pitch, yaw):
        """
        Converts Euler angles to a rotation matrix.
        
        Args:
            roll: Rotation around the x-axis in degrees.
            pitch: Rotation around the y-axis in degrees.
            yaw: Rotation around the z-axis in degrees.
        
        Returns:
            A 3x3 rotation matrix.
        """
        
        # Compute individual rotation matrices
        R_x = numpy.array([[1, 0, 0],
                           [0, numpy.cos(roll), -numpy.sin(roll)],
                           [0, numpy.sin(roll),  numpy.cos(roll)]])

        R_y = numpy.array([[ numpy.cos(pitch), 0, numpy.sin(pitch)],
                           [0, 1, 0],
                           [-numpy.sin(pitch), 0, numpy.cos(pitch)]])

        R_z = numpy.array([[numpy.cos(yaw), -numpy.sin(yaw), 0],
                           [numpy.sin(yaw),  numpy.cos(yaw), 0],
                           [0, 0, 1]])

        # Combined rotation matrix
        self.matrix = R_z @ R_y @ R_x
        return self.matrix
    
    def matrix_to_euler(self):
        """
        Convert a rotation matrix to Euler angles (roll, pitch, yaw) following the X-Y-Z intrinsic rotation sequence.

        Parameters:
        R (numpy.ndarray): A 3x3 rotation matrix.

        Returns:
        tuple: A tuple containing the Euler angles (roll, pitch, yaw) in degrees,
            each ranging from -180 to 180 degrees.
        """
        
        # # Validate the input matrix
        # if not isinstance(self.matrix, numpy.ndarray):
        #     raise TypeError("Input must be a numpy ndarray.")
            
        # if self.matrix.shape != (3, 3):
        #     raise ValueError("Input rotation matrix must be a 3x3 matrix.")
        
        # # Check if the matrix is orthogonal and has determinant +1
        # if not numpy.allclose(numpy.dot(self.matrix, self.matrix.T), numpy.identity(3), atol=1e-6):
        #     raise ValueError("Input matrix is not orthogonal.")
            
        # if not numpy.isclose(numpy.linalg.det(self.matrix), 1.0, atol=1e-6):
        #     raise ValueError("Input matrix must have a determinant of +1.")
        
        # Extract the elements of the rotation matrix
        r11, r12, r13 = self.matrix[0, 0], self.matrix[0, 1], self.matrix[0, 2]
        r21, r22, r23 = self.matrix[1, 0], self.matrix[1, 1], self.matrix[1, 2]
        r31, r32, r33 = self.matrix[2, 0], self.matrix[2, 1], self.matrix[2, 2]
        
        # Compute the pitch angle theta
        # Clamp the value to avoid numerical issues with arcsin
        theta_rad = numpy.arcsin(-numpy.clip(r31, -1.0, 1.0))
        theta_deg = numpy.degrees(theta_rad)
        
        # Compute cos(theta) to check for gimbal lock
        cos_theta = numpy.cos(theta_rad)
        
        # Define a small threshold to check if cos(theta) is close to zero
        EPS = 1e-6
        
        if abs(cos_theta) > EPS:
            # No gimbal lock
            phi_rad = numpy.arctan2(r32, r33)  # Roll
            psi_rad = numpy.arctan2(r21, r11)  # Yaw
        else:
            # Gimbal lock occurs
            # Set roll to zero and compute yaw based on available information
            phi_rad = 0.0
            if r31 <= -1.0:
                # theta = +90 degrees
                psi_rad = numpy.arctan2(-r12, r22)
            else:
                # theta = -90 degrees
                psi_rad = numpy.arctan2(r12, r22)
        
        # Convert radians to degrees
        phi_deg = numpy.degrees(phi_rad)
        psi_deg = numpy.degrees(psi_rad)
        
        # Normalize the angles to be within -180 to 180 degrees
        def normalize_angle(angle):
            """
            Normalize an angle to be within the range [-180, 180] degrees.

            Parameters:
            angle (float): Angle in degrees.

            Returns:
            float: Normalized angle in degrees.
            """
            return ((angle + 180) % 360) - 180
        
        phi_deg = normalize_angle(phi_deg)
        theta_deg = normalize_angle(theta_deg)
        psi_deg = normalize_angle(psi_deg)
        
        return (phi_deg, theta_deg, psi_deg)
    
    
class SlidingWindow:
    """
    A sliding window buffer maintains the most recent N samples 
    required for operations like moving average and adaptive thresholding.
    """
    def __init__(self, size):
        self.size = size        # window size
        self.buffer = []        # window content
        self.cumsum = 0.0       # maintain cumulative sum of the window
        self.cumsum_sq = 0.0    # maintain cumulative squared sum of the window

    def add_sample(self, sample):
        # New sample arrived
        self.buffer.append(sample)
        
        # update the window content and statistics
        # append most new sample and pop most old sample
        self.cumsum += sample
        self.cumsum_sq += sample ** 2
        if len(self.buffer) > self.size:
            removed = self.buffer.pop(0)
            self.cumsum -= removed
            self.cumsum_sq -= removed ** 2

    def get_mean(self):
        # Get average value of the window
        # Handle buffer not available case
        if not self.buffer:
            return 0.0
        
        return self.cumsum / len(self.buffer)

    def get_std(self):
        # Get standard derivation value of the window
        # Handle buffer not available case
        if not self.buffer:
            return 0.0
        
        mean = self.get_mean()
        variance = (self.cumsum_sq / len(self.buffer)) - (mean ** 2)
        return variance ** 0.5 if variance > 0 else 0.0

    def get_window(self):
        # Get the window
        return self.buffer.copy()