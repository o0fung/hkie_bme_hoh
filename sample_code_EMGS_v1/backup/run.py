import traceback
import os
import time
import argparse
import numpy
import data

from matplotlib import pyplot


DIRPATH = 'data_20250203073445_dumbbell_exercise'


class Operation:
    
    def __init__(self, data=None, skip_filter=False):
        self.path = ''
        
        if data is not None:
            if skip_filter:
                self.load_data_from_raw(data)
            else:
                self.load_data_from_ui(data)
                
    def set_path(self, path):
        self.path = path
        
        buffer = {'icm': None, 'emg': None}

        # Load ICM data
        with open(os.path.join(path, 'icm.data'), 'rb') as f:
            buffer['icm'] = numpy.load(f, allow_pickle=True)
            
        # Load EMG data
        with open(os.path.join(path, 'emg.data'), 'rb') as f:
            buffer['emg'] = numpy.load(f, allow_pickle=True)
            
        self.load_data_from_raw(buffer)
        
    def load_data_from_raw(self, data):
        # Load data that has already been processed
        self.icm = data['icm']
        self.emg = data['emg']
        
    def load_data_from_ui(self, data):
        # Load the data to numpy structured array
        # Filter the missing data, i.e. rows where Time and Data are both zeros
        self.icm_0 = data['icm'][data['icm']['icmT'] != 0]
        self.emg_0 = data['emg'][data['emg']['emgT'] != 0]
        
        # Unit of ICM time is 10ms, so should multipy it by 10
        self.icm_0['icmT'] *= 10.0

        # Previously the first row with Time=0 have also been filtered
        # Now recover the first row for complete data set
        self.icm = numpy.concatenate(([data['icm'][0]], self.icm_0))
        self.emg = numpy.concatenate(([data['emg'][0]], self.emg_0))
    
    def save_data(self, path=None):
        # Save all data to files for future use
        
        if path is not None:
            path_to_data = path
        else:
            # Setup a new folder with the current timestamp
            path_to_data = os.path.join(os.path.dirname(__file__), time.strftime('data_%Y%m%d%H%M%S'))
            if not os.path.exists(path_to_data):
                os.mkdir(path_to_data)
        
        # Save ICM data as CSV file
        with open(os.path.join(path_to_data, 'icm.csv'), 'wb') as f:
            numpy.savetxt(f, self.icm, delimiter=',', header=','.join(self.icm.dtype.names), fmt='%f'+',%f'*(len(self.icm.dtype.names)-1), comments='')
        
        # Save EMG data as CSV file
        with open(os.path.join(path_to_data, 'emg.csv'), 'wb') as f:
            numpy.savetxt(f, self.emg, delimiter=',', header=','.join(self.emg.dtype.names), fmt='%f'+',%f'*(len(self.emg.dtype.names)-1), comments='')
            
        # Save ICM data as Numpy data file
        with open(os.path.join(path_to_data, 'icm.data'), 'wb') as f:
            numpy.save(f, self.icm, allow_pickle=True)
            
        # Save EMG data as Numpy data file
        with open(os.path.join(path_to_data, 'emg.data'), 'wb') as f:
            numpy.save(f, self.emg, allow_pickle=True)
            
    def show_fig(self):
        pyplot.show()        
    
    def save_fig(self, path=None, fname=None):
        # Save all data to figure for future use
        
        if path is not None:
            path_to_data = path
        
        else:
            # Setup a new folder with the current timestamp
            path_to_data = os.path.join(os.path.dirname(__file__), time.strftime('data_%Y%m%d%H%M%S'))
            if not os.path.exists(path_to_data):
                os.mkdir(path_to_data)
        
        if fname is not None:
            fpath = f'{fname}.png'
        else:
            fpath = 'fig.png'
        
        manager = pyplot.get_current_fig_manager()
        manager.full_screen_toggle()
        
        # Save figure as png file
        with open(os.path.join(path_to_data, fpath), 'wb') as f:
            pyplot.savefig(f)
            
    def display(self):
        # Display all data in one figure for reference
        
        with pyplot.ion():
        
            fig, ax = pyplot.subplots(4, 1, sharex=True, num='Display All')
            
            ax[0].plot(self.icm['icmT'], self.icm['accX_'] +1, color='b')
            ax[0].plot(self.icm['icmT'], self.icm['accY_'] +1, color='r')
            ax[0].plot(self.icm['icmT'], self.icm['accZ_'] +1, color='g')
            ax[0].set_ylabel('Acc (g)')
            ax[0].set_title('Accelerometer (ACC)')
            ax[0].grid(True, which='both', axis='both')
            
            ax[1].plot(self.icm['icmT'], self.icm['gyrX_'] +1, color='b')
            ax[1].plot(self.icm['icmT'], self.icm['gyrY_'] +1, color='r')
            ax[1].plot(self.icm['icmT'], self.icm['gyrZ_'] +1, color='g')
            ax[1].set_ylabel('Gyr (deg/s)')
            ax[1].set_title('Gyroscope (GYR)')
            ax[1].grid(True, which='both', axis='both')
            
            ax[2].plot(self.icm['icmT'], self.icm['magX_'], color='b')
            ax[2].plot(self.icm['icmT'], self.icm['magY_'], color='r')
            ax[2].plot(self.icm['icmT'], self.icm['magZ_'], color='g')
            ax[2].set_ylabel('Mag (mT)')
            ax[2].set_title('Magnetometer (MAG)')
            ax[2].grid(True, which='both', axis='both')
            
            ax[3].plot(self.emg['emgT'], self.emg['emg'])
            ax[3].set_ylabel('EMG (mV)')
            ax[3].set_xlabel('Time (ms)')
            ax[3].set_title('Electromyography (EMG)')
            ax[3].grid(True, which='both', axis='both')
    
    def work_on_ui(self):
        # Suppose to run in User Interface
        
        try:
            self.save_data()
            self.display()
            
        except Exception as e:
            traceback.print_exc()
            
        except SyntaxError:
            pass
        
    def work_on_cli(self):
        # Suppose to run in Command Prompt Terminal
        
        try:
            # Pulse detector optimization parameters

            # Prepare memory to store all data to be processed
            length_icm = self.icm.shape[0]
            length_emg = self.emg.shape[0]
            self.output = data.Data()
            self.output.set_zero(n_icm=length_icm, n_emg=length_emg)
            self.output.set_pulse_detector(
                max_threshold=150,
                min_threshold=30,
                max_pulse_width=500,
                min_pulse_width=100,
                max_pulse_width_critical=300,
                min_pulse_width_critical=120,
                max_peak_loc_critical=0.7,
                min_peak_loc_critical=0.3,
            )
            # self.output.set_pulse_detector(
            #     max_threshold=150,
            #     min_threshold=30,
            #     max_pulse_width=500,
            #     min_pulse_width=100,
            #     max_pulse_width_critical=300,
            #     min_pulse_width_critical=120,
            #     max_peak_loc_critical=0.7,
            #     min_peak_loc_critical=0.3,
            # )
            self.output.load_data(icm=self.icm, emg=self.emg)
            
            # For counting the time elaspse
            t0 = time.time()
            
            # Loop through every ICM data frame
            for n in range(1, length_icm):
                
                self.output.add_data_buffer('accT', n * 10.0 / 1000.0)
                self.output.add_data_buffer('gyrT', n * 10.0 / 1000.0)
                self.output.add_data_buffer('magT', n * 10.0 / 1000.0)
                self.output.compute_from_icm(n)
                
                # For every ICM data frame, there will be 10 EMG data frames
                for i in range(10):
                    nn = n*10+i
                    self.output.add_data_buffer('emgT', nn / 1000.0)
                    self.output.add_data_buffer('emg', self.emg['emg'][nn])
                    self.output.add_data_buffer('rms100', self.emg['emg'][nn])
                    self.output.compute_from_emg(nn)
                
                print(time.strftime(f"Time elapse: %H:%M:%S\tProgress: {n/length_icm*100:1.1f} %% \tFrame Count: {nn}\r", time.gmtime(time.time() - t0)), end='')
            
            print('')

            self.pulses, self.critical_pulses = [], []            
            for i in range(len(self.output.pulse_detect)):
                self.pulses.append(self.output.pulse_detect[i].get_pulses())
                self.critical_pulses.append(self.output.pulse_detect[i].get_critical_pulses())
            
        except Exception as e:
            traceback.print_exc()
            
        except SyntaxError:
            pass
        
    def plot_angle_emg_all(self):
        # Plotting graphs
        fig, ax = pyplot.subplots(4, 1, sharex=True, num='EMGS Data All')
        
        x = 0
        ax[x].plot(self.output.data['icm']['icmT'], self.output.data['icm']['pitch_'], color='r')
        ax[x].axhline(y=0, color='k', alpha=0.5, linestyle=':')
        ax[x].set_title('Pitch (red) Angle (degree)')
        ax[x].grid(True, which='both', axis='both')

        x += 1
        ax[x].plot(self.output.data['icm']['icmT'], self.output.data['icm']['roll_'], color='b')
        ax[x].plot(self.output.data['icm']['icmT'], self.output.data['icm']['yaw_'], color='g')
        ax[x].axhline(y=0, color='k', alpha=0.5, linestyle=':')
        ax[x].set_title('Roll (blue) & Yaw (green) Angle (degree)')
        ax[x].grid(True, which='both', axis='both')

        x += 1
        ax[x].plot(self.output.data['emg']['emgT'], self.output.data['emg']['emg'], color='k', alpha=0.3)
        ax[x].plot(self.output.data['emg']['emgT'], self.output.data['emg']['rms'], color='r')
        ax[x].axhline(y=0, color='k', alpha=0.5, linestyle=':')
        ax[x].set_title('EMG (mV)')
        ax[x].grid(True, which='both', axis='both')
        
        x += 1
        ax[x].plot(self.output.data['emg']['emgT'], self.output.data['emg']['mnf'], color='b', alpha=0.3)
        ax[x].plot(self.output.data['emg']['emgT'], self.output.data['emg']['mdf'], color='g', alpha=0.3)
        ax[x].axhline(y=0, color='k', alpha=0.5, linestyle=':')
        ax[x].set_title('Frequency of EMG (Hz)')
        ax[x].grid(True, which='both', axis='both')
        
        x += 1
        
        for j in range(len(self.output.pulse_detect)):
            for pulse in self.pulses[j]:
                if pulse in self.critical_pulses[j]:
                    print(f'{pulse} ' + '*' * (j+1))
                    color = 'rb'[j]
                else:
                    print(pulse)
                    color = 'k'
                
                for i in range(x):
                    ax[i].axvspan(xmin=pulse['start'] * 10,
                                xmax=pulse['end'] * 10,
                                color=color, alpha=0.1)
                
    def plot_angle_emg_per_pulse(self, pulse_id):
        # Plotting graphs
        fig, ax = pyplot.subplots(3, 2, num='EMGS Data Per Pulse')
        
        array = []
        for pulse in self.pulses[pulse_id]:
            samples = self.output.data['icm']['pitch'][pulse['start'] : pulse['end']]
            array.append(max(samples))
        ax[0][0].bar(numpy.arange(len(array)), array)
        ax[0][0].plot(numpy.arange(len(array)), array, color='k')
        ax[0][0].set_title('Max Pitch Angle of Arm at Flexion (degree)')
        ax[0][0].set_ylim([0, 90])
        
        array = []
        pulse_end = None
        for pulse in self.pulses[pulse_id]:
            if pulse_end is not None:
                samples = self.output.data['icm']['pitch'][pulse_end : pulse['start']]
            pulse_end = pulse['end']
            array.append(min(samples))
        ax[0][1].bar(numpy.arange(len(array)), array)
        ax[0][1].plot(numpy.arange(len(array)), array, color='k')
        ax[0][1].set_title('Max Pitch Angle of Arm at Extension (degree)')
        ax[0][1].set_ylim([0, 90])
        
        array = []
        for pulse in self.pulses[pulse_id]:
            samples = self.output.data['icm']['roll'][pulse['start'] : pulse['end']]
            array.append(max(samples))
        ax[1][0].bar(numpy.arange(len(array)), array)
        ax[1][0].plot(numpy.arange(len(array)), array, color='k')
        ax[1][0].set_title('Max Roll Angle of Arm at Flexion (degree)')
        ax[1][0].set_ylim([0, 90])
        
        array = []
        pulse_end = None
        for pulse in self.pulses[pulse_id]:
            if pulse_end is not None:
                samples = self.output.data['icm']['roll_'][pulse_end : pulse['start']]
            pulse_end = pulse['end']
            array.append(min(samples))
        ax[1][1].bar(numpy.arange(len(array)), array)
        ax[1][1].plot(numpy.arange(len(array)), array, color='k')
        ax[1][1].set_title('Max Roll Angle of Arm at Extension (degree)')
        ax[1][1].set_ylim([0, 90])
        
        array = []
        for pulse in self.pulses[pulse_id]:
            samples = self.output.data['emg']['rms'][pulse['start']*10 : pulse['end']*10]
            array.append(max(samples))
        ax[2][0].bar(numpy.arange(len(array)), array)
        ax[2][0].plot(numpy.arange(len(array)), array, color='k')
        ax[2][0].set_title('Max EMG RMS (mV)')
        ax[2][0].set_xlabel('Repetition')
        
        array = []
        for pulse in self.pulses[pulse_id]:
            samples = self.output.data['emg']['mnf'][pulse['start']*10 : pulse['end']*10]
            array.append(numpy.mean(samples))
        ax[2][1].bar(numpy.arange(len(array)), array, color='b', width=0.25)
        ax[2][1].plot(numpy.arange(len(array)), array, color='b')
        
        array = []
        for pulse in self.pulses[pulse_id]:
            samples = self.output.data['emg']['mdf'][pulse['start']*10 : pulse['end']*10]
            array.append(numpy.mean(samples))
        ax[2][1].bar(numpy.arange(len(array))+0.25, array, color='r', width=0.25)
        ax[2][1].plot(numpy.arange(len(array))+0.25, array, color='r')
        
        ax[2][1].set_title('Average EMG MNF (blue) MDF (red)')
        ax[2][1].set_xlabel('Repetition')
        
            
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
    work = Operation(buffer, skip_filter=True)
    work.set_path(args['path'])
    
    work.work_on_cli()
    work.plot_angle_emg_all()
    # work.save_fig(path=args['path'], fname='EMGS_Data_All')
    work.show_fig()
    work.plot_angle_emg_per_pulse(0)
    # work.save_fig(path=args['path'], fname='EMGS_Data_Per_Pulse')
    work.show_fig()
    