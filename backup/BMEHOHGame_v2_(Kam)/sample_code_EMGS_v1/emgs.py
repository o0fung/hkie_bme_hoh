import run1_data_processing
import data_model


class EMGS:
    list_str_icm_mode = [
        'raw_acc',
        'cal_acc',
        'lin_acc',
        'raw_gyr',
        'cal_gyr',
        'raw_mag',
        'cal_mag',
        'quat_vec',
        'quat_mag',
    ]
    list_str_imu_sensor = {
        1: 'acc',
        4: 'gyr',
        6: 'mag',
    }
    list_str_battery = {
        'low': 3.1 * 50,
        'high': 4.15 * 50,
    }

    def __init__(self, addr):
        self.client = None
        self.addr = addr
        
        self.is_connected = False
        self.is_streaming = False
        self.is_charging = False
        
        self.name = ''
        self.ver_fw = ''
        self.ver_hw = ''
        self.ver_sw = ''
        self.timestamp = 0
        self.battery = 0
        
        self.emg_mode = 0
        self.icm_mode = {}
        for mode in self.list_str_icm_mode:
            self.icm_mode[mode] = False
        
        self.signal = data_model.Data()
        self.t0 = 0.0
        self.ptr_icm_analysis = 0
        
    def data_processing(self):
        # Trigger the data processing algorithm
        work = run1_data_processing.Operation()
        work.set_path('data')
        work.load_data_from_raw(self.signal.data)
        work.save_data_from_raw()
        