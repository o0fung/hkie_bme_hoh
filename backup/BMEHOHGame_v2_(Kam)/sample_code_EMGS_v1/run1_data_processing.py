import traceback
import os
import time
import argparse
import numpy
import data_model

from matplotlib import pyplot


DIRPATH = 'data_20250203073445_dumbbell_exercise'


class Operation:
    """ Data Processing to Extract Useful Features from Data """
    
    def __init__(self):
        self.path = ''
        
    def set_path(self, path):
        """ Define the directory path for database """
        self.path = path
        
    def load_data_from_raw(self, data):
        # Load data that has already been processed
        self.icm = data['icm']
        self.emg = data['emg']
        
    def load_data_from_file(self):
        """ Load the data into buffer """
        path = self.path
        buffer = {'icm': None, 'emg': None}

        # Load ICM data
        with open(os.path.join(path, 'icm.data'), 'rb') as f:
            buffer['icm'] = numpy.load(f, allow_pickle=True)
            
        # Load EMG data
        with open(os.path.join(path, 'emg.data'), 'rb') as f:
            buffer['emg'] = numpy.load(f, allow_pickle=True)
            
        # Load data that has already been processed
        self.icm = buffer['icm']
        self.emg = buffer['emg']
        
    def process_data(self):
        """ Data processing """
        length_icm = self.icm.shape[0]
        length_emg = self.emg.shape[0]
        
        """ Generate new data columns with derived features """
        self.output = data_model.Data()
        self.output.set_zero(n_icm=length_icm, n_emg=length_emg)
        self.output.load_data(icm=self.icm, emg=self.emg)
        self.output.process_data()
        
    def save_data(self, path=None, suffix=''):
        """ Save the processed ICM data to icm_normalized.csv """
        if path is not None:
            self.output.save_data(path, suffix)  
        else:
            self.output.save_data(self.path, suffix)
            
    def save_data_from_raw(self, path=None):
        """ Save/overwrite the raw data to the path 
            in case the raw data was not fully generated at run-time
            (including emg.csv, emg.data, icm.csv, and icm.data)
        """
        
        if path is not None:
            path_to_data = path
        else:
            # Setup a new folder with the current timestamp
            path_to_data = os.path.join(self.path, time.strftime('data_%Y%m%d%H%M%S'))
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
        
        fig, ax = pyplot.subplots(1, 1, num='All Normalized Data Channels')
        
        length_ch = len(self.output.list_str_channel_normalized)
        
        for n, ch in enumerate(self.output.list_str_channel_normalized):
            ax.plot(self.output.data['icm']['icmT'], self.output.data['icm'][ch] + (length_ch - n) * 4 - 2)
        
        ax.set_ylabel('Features')
        ax.set_xlabel('Index')
        ax.grid(True, which='both', axis='both')
        
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
        

if __name__ == '__main__':
    # parse from command line the target data directory path
    parser = argparse.ArgumentParser(description='Select File for Data Processing')
    parser.add_argument('path', help='target directory path to data')
    args = vars(parser.parse_args())
    
    # Run the data algorithm
    work = Operation()
    print(f'>> Data Processing')

    work.set_path(args['path'])
    print(f'>> Data path: {args["path"]}')

    work.load_data_from_file()
    print(f'>> Data loading successfully. (ICM Data Size: {work.icm.shape})')
    
    work.process_data()
    print(f'>> Data processing successfully.')

    work.save_data(suffix='normalized')
    print(f'>> Data saved to csv file successfully.')
    
    # work.save_data_from_raw(args["path"])

    # work.plot_angle_emg_all()
    # work.show_fig()
    