import argparse
import numpy
import os
import re

from matplotlib import pyplot


DEFAULT_PATH = 'data/data_20250203073445_dumbbell_exercise'


class Operation:
    """ Data Labelling to Update Class Label of Data """
    def __init__(self):
        self.path = DEFAULT_PATH
        self.labels = None
    
    def set_path(self, path):
        """ Define the directory path for database """
        self.path = path
        
    def load_data(self):
        """ Load data file to memory """
        # IMU data
        path_imu = os.path.join(self.path, 'icm_normalized.csv')
        self.imu = numpy.genfromtxt(path_imu, delimiter=',', names=True)
        # EMG data
        path_emg = os.path.join(self.path, 'emg.csv')
        self.emg = numpy.genfromtxt(path_emg, delimiter=',', names=True)
        
        # Strip the end of the dataset for any zero pad
        self.imu = self.imu[: numpy.nonzero(self.imu['icmT'])[0][-1] + 1]
        self.emg = self.emg[: numpy.nonzero(self.emg['emgT'])[0][-1] + 1]
        
        # Fix the issue some row of data has no timestamp column
        for i in range(self.imu.shape[0]):
            if self.imu['icmT'][i] == 0:
                self.imu['icmT'][i] = i * 10
        
        for i in range(self.emg.shape[0]):
            if self.emg['emgT'][i] == 0:
                self.emg['emgT'][i] = i
        
    def load_label(self):
        """ Load label to memory """
        path = os.path.join(self.path, 'label.csv')
        if not os.path.exists(path):
            print(f'>>! No label file exist.')
            self.labels = None
            return
            
        self.labels = numpy.genfromtxt(path, delimiter=',', dtype=int, names=True)
        
    def save_label(self):
        """ Save label from memory """
        path = os.path.join(self.path, 'label.csv')
        
        with open(path, 'wb') as f:
            numpy.savetxt(f, self.labels, delimiter=',', comments='', header=','.join(self.labels.dtype.names), fmt='%d' + ',%d' * (len(self.labels.dtype.names)-1))
        
    def label_data(self, path_png=None):
        """ Plot the data and enable cursor selection for labelling """
        tool = LabellingTool(self.imu, self.emg, self.labels)
        tool.show()
        
        if path_png is not None:
            path_png = os.path.join(self.path, path_png)
            tool.fig.savefig(path_png)
        
        self.labels = tool.labels
        return self.labels
    
    
class LabellingTool:
    """ Plot relevant data for user to select event labelling
          User click on the plot to select start/end events
          User type and enter event types
    """
    
    def __init__(self, data_imu, data_emg, labels=None):
        """ Plot data for mouse cursor click selection """
        if labels is not None:
            self.labels = labels                           # output label array
        else:
            self.labels = numpy.zeros(data_imu.shape[0], dtype=[('label', 'i')])     
        
        self.current_event_type = 0                         # class label type in number
        self.current_event_group = 'label'                       # class label group in number
        self.event_type_buffer = ''
        self.start_index = None                             # currently selected start and end indices
        self.end_index = None
        self.start_lines = []
        self.end_lines = []
        self.event_shades = []
        
        self.data_imu = data_imu                            # data array and time array
        self.time_imu = data_imu['icmT']
        self.data_emg = data_emg
        self.time_emg = data_emg['emgT']
        
        # Setup plot
        self.fig, self.ax = pyplot.subplots(8, 1, sharex=True, figsize=(12, 8))
        # Full screen
        mng = pyplot.get_current_fig_manager()
        mng.full_screen_toggle()
        # Draw subplots index #n
        n = 0
        self.ax[n].plot(self.time_imu, self.data_imu['roll_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['roll_s']*90, color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['roll_c']*90, color='g')
        self.ax[n].set_ylabel('roll_')
        n += 1
        self.ax[n].plot(self.time_imu, self.data_imu['pitch_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['pitch_s']*90, color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['pitch_c']*90, color='g')
        self.ax[n].set_ylabel('pitch_')
        n += 1
        self.ax[n].plot(self.time_imu, self.data_imu['yaw_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['yaw_s']*90, color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['yaw_c']*90, color='g')
        self.ax[n].set_ylabel('yaw_')
        n += 1
        self.ax[n].plot(self.time_imu, self.data_imu['accX_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['accY_'], color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['accZ_'], color='g')
        self.ax[n].set_ylabel('accXYZ_')
        n += 1
        self.ax[n].plot(self.time_imu, self.data_imu['gyrX_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['gyrY_'], color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['gyrZ_'], color='g')
        self.ax[n].set_ylabel('gyrXYZ_')
        n += 1
        self.ax[n].plot(self.time_imu, self.data_imu['magX_'], color='b')
        self.ax[n].plot(self.time_imu, self.data_imu['magY_'], color='r')
        self.ax[n].plot(self.time_imu, self.data_imu['magZ_'], color='g')
        self.ax[n].set_ylabel('magXYZ_')
        n += 1
        self.ax[n].plot(self.time_emg, self.data_emg['emg'], color='b')
        self.ax[n].set_ylabel('emg')
        n += 1
        
        for i in range(n):
            # Draw reference grid lines and zero line for visualization purpose
            self.ax[i].axhline(y=0, color='k', alpha=0.5, linestyle=':')
            self.ax[i].grid(True, which='both', axis='both')
            self.ax[i].autoscale(False)
            self.start_lines.append(self.ax[i].axvline(x=0, color='k', linestyle='-'))
            self.end_lines.append(self.ax[i].axvline(x=0, color='k', linestyle='--'))
        
        for name in self.labels.dtype.names:
            self.ax[n].plot(self.time_imu, self.labels[name], label=name)
        self.ax[n].set_ylabel('Labels')
        self.ax[n].set_xlabel('time (ms)')
        self.ax[n].legend()
        
        self.update_message()
        
        pyplot.tight_layout()
        
        # Connect event handlers
        self.cid_click = self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.cid_key = self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
    
    def on_click(self, event):
        if event.inaxes not in self.ax:
            return          # Click was outside the data axes
        
        # Get the x-value of the click
        x = event.xdata
        # Find the nearest index
        idx = numpy.searchsorted(self.time_imu, x)
        if idx >= len(self.time_imu):    
            idx = len(self.time_imu) - 1
        
        if event.button == 1:
            # Left click: select start index
            self.change_event_index(idx, is_start=True)
            
        elif event.button == 3:
            # Right click: select end index
            self.change_event_index(idx, is_start=False)
            
        else:
            # Other mouse click: ignored
            pass
        
    def change_event_index(self, idx, is_start):
        line_idx = 0
        
        if is_start:
            for i in range(7):
                self.start_lines[i].remove()
            
            # Start event identified
            self.start_index = idx
            # Remove all start lines before adding new start line
            for i in range(7):
                if idx is not None:
                    line_idx = self.start_index
                
                self.start_lines[i] = self.ax[i].axvline(x=self.time_imu[line_idx], color='k', linestyle='-')
            
        else:
            for i in range(7):
                self.end_lines[i].remove()
            
            # End event identified
            self.end_index = idx
            # Remove all end lines before adding new start line
            for i in range(7):
                if idx is not None:
                    line_idx = self.end_index
                    
                self.end_lines[i] = self.ax[i].axvline(x=self.time_imu[line_idx], color='k', linestyle='--')
        
        self.update_message()
        
        self.fig.canvas.draw()      # Update the plot
            
    def assign_label(self):
        if self.start_index is not None and self.end_index is not None:
            self.labels[self.current_event_group][self.start_index: self.end_index] = self.current_event_type
            
            self.ax[7].clear()
            for name in self.labels.dtype.names:
                self.ax[7].plot(self.time_imu, self.labels[name], label=name)
            self.ax[7].legend()
            
            self.fig.canvas.draw()
        
    def on_key_press(self, event):
        key = event.key
        
        # Handle special keys
        if key == 'enter':
            # Turn the character in the buffer into string and number
            # And apply to the event type and group
            if self.event_type_buffer:
                re_result = re.findall(r"^([a-zA-Z]*)(\d*)", self.event_type_buffer)
                if re_result:
                    self.current_event_type = int(re_result[0][1]) if re_result[0][1] else self.current_event_type
                    self.current_event_group = re_result[0][0] if re_result[0][0] else self.current_event_group
                    
                    if not self.current_event_group in self.labels.dtype.names:
                        # Add the new event group to the current label array
                        new_dtype = self.labels.dtype.descr + [(self.current_event_group, 'i')]
                        new_labels = numpy.zeros(self.labels.shape, dtype=new_dtype)
                        for name in self.labels.dtype.names:
                            new_labels[name] = self.labels[name]
                        self.labels = new_labels
                    
                self.event_type_buffer = ''
            else:
                self.current_event_type = 0
                self.current_event_group = 'label'
                
        elif key == ' ':
            # Identified the Start End Range, assign label to range
            self.assign_label()
                
        elif key == 'backspace':
            # Remove the last character in the buffer
            if self.event_type_buffer:
                self.event_type_buffer = self.event_type_buffer[:-1]
                
        elif len(key) == 1 and key.isalnum():
            # Append only numeric characters
            self.event_type_buffer += key
            
        elif key == 'escape':
            pyplot.close()
            return
            
        else:
            pass        # ignore other key input
        
        # Reset the cursor
        self.change_event_index(None, is_start=True)
        self.change_event_index(None, is_start=False)
            
        self.update_message()
        self.fig.canvas.draw()
    
    def update_message(self):
        self.fig.suptitle(
            f"Selected: Start [ {self.start_index} ] / End [ {self.end_index} ] -> Current Label: {self.current_event_group} {self.current_event_type} (Label Type Buffer: {self.event_type_buffer})",
            fontsize=16)
        self.ax[0].set_title('<Left Click> select START <Right Click> select END <Spacebar> assign label <A-z0-9> change label type buffer <Enter> confirm label type change <ESC> quit and apply label changes <Any key> cancel selection',
                             fontsize=10)
    
    def show(self):
        pyplot.show()
            

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Select File for Data Labelling')
    parser.add_argument('path', help='target directory path to data', default=DEFAULT_PATH, nargs='?')
    args = vars(parser.parse_args())
    
    # Run the data labelling work flow
    work = Operation()
    print(f'>> Data Labelling')
    
    work.set_path(args['path'])
    print(f'>> Data path: {args["path"]}')
    
    work.load_label()
    work.load_data()
    print(f'>> Load data and labels successfully.')
    
    work.label_data()
    print(f'>> Updated data labelling.')
    
    work.save_label()
    print(f'>> Save labels successfully.')
    