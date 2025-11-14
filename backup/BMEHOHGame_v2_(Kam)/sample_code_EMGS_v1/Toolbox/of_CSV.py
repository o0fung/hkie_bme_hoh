import csv          # For reading and writing CSV files.
import numpy        # For performing array operations.
import shutil       # For file manipulation, such as creating backup copies.
import os           # For file operations, such as removing files.


class Helper:
    # The Helper class contains methods to handle CSV files, 
    # including - 
    #       Read headers from a CSV file or generate default headers.
    #       Ensure all rows in the CSV file have consistent lengths.
    #       Read the CSV data into a NumPy array for further processing.
    
    def __init__(self, path, header=None):
        self.path = path            # Stores the file path to the CSV file.
        self.header = header        # Stores the header of the CSV file.
        self.skip_header = 0        # Indicating how many rows to skip when reading data
        
    def get_header(self, row=0):
        # construct the header as #0, #1, #2, ...
        #   or use the header row if the data file provided
        if row:
            # header available: reads the specified row as the header.
            self.skip_header = row + 1
            with open(self.path, 'r', encoding='utf-8-sig') as f:
                for _ in range(row):
                    f.readline()        # skip rows above header
                
                # get the header text string, by remove newline, space
                self.header = ','.join(f.readline().strip(',\n').replace(' ', '').split(','))
        else:
            # no header available: constructs a header with column names like #0, #1, etc.
            with open(self.path, 'r', encoding='utf-8-sig') as f:
                # find out the number of column on the first row
                ncol = len(f.readline().strip(',\n').replace(' ', '').split(','))
                
                # construct the header as a numbered index
                self.header = ','.join([f'#{str(x)}' for x in numpy.arange(ncol)])
            
        return self.header
    
    def fix_row_length(self):
        # Ensures all rows in the original CSV file 
        # have the same length as the header by padding empty cells.
                
        # Creates a backup of the CSV file.
        backup_filepath = self.path.replace('.csv', '_backup.csv')
        shutil.copy(self.path, backup_filepath)

        with open(backup_filepath, 'r') as f_in, open(self.path, 'w', newline='') as f_out:
            # csv file read/write objects
            csv_reader = csv.reader(f_in, delimiter=',')
            csv_writer = csv.writer(f_out, delimiter=',')

            for i, row in enumerate(csv_reader):
                # padding empty cells if the row has varying length
                if i >= self.skip_header:
                    row = row + [''] * (len(self.header) - len(row))

                # Writes the fixed rows to the original file.
                csv_writer.writerow(row)
        
        # Removes the backup file after processing.
        os.remove(backup_filepath)
    
    def read_raw_data(self, dtype=None):
        # Reads the CSV file into a NumPy array using numpy.genfromtxt.
        # Uses the header and skips the appropriate number of rows.
        
        with open(self.path, mode='r', encoding='utf-8-sig') as f:
            # read raw data
            self.array = numpy.genfromtxt(
                f,
                delimiter=',',
                names=self.header,
                dtype=dtype,
                usecols=range(0, len(self.header.split(','))),
                skip_header=self.skip_header,
                encoding=None, )
            
        # Stores the array and its length.
        self.length = len(self.array)
        
        # Returns the NumPy array.
        return self.array
    
        
if __name__ == '__main__':
    
    PATH0 = 'test0_csv.csv'
    header_str = ('#', 'time', 'data')
    with open(PATH0, mode='r', encoding='utf-8-sig') as f:
        data0 = numpy.genfromtxt(f, names=','.join(header_str), delimiter=',')
    print(data0['data'])
    
    PATH1 = 'test1_csv.csv'
    header_str = ('#', 'time', 'data')
    data1 = Helper(PATH1, header=header_str)
    data1.read_raw_data()
    print(data1.array['data'])
    
    PATH2 = 'test2_csv.csv'
    data2 = Helper(PATH2)
    data2.get_header(row=1)
    for row in data2.read_raw_data(dtype='float'):
        print(row)
    