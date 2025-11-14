import numpy
import os

from sklearn.utils import shuffle as sklearn_shuffle


class DataPreparer:
    def __init__(self, random_state=42):
        """
        Initializes the DataPreparer with paths to data and labels CSV files
        and other configuration parameters.

        :param random_state: Seed used by the random number generator.
        """
        self.random_state = random_state

        # Attributes to be populated
        self.batches_data = []
        self.batches_label = []
        self.batches_time = []
        self.windowed_X = None
        self.windowed_y = None
        self.windowed_t = None
        
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        
        self.features = []
        self.means = {}
        self.stds = {}

    def load_data(self, data_csv_path, labels_csv_path, data_col=None, label_type='label'):
        """Loads data and labels from CSV files using NumPy.
        :param data_csv_path: Path to the dataset CSV file.
        :param labels_csv_path: Path to the labels CSV file.
        :param label_type: select which column of label be considered in the model
        """
        if not os.path.exists(data_csv_path):
            print(f">> Data file not found: {data_csv_path}")
            return
        if not os.path.exists(labels_csv_path):
            print(f">> Labels file not found: {labels_csv_path}")
            return

        # Load dataset
        if data_col is not None:
            self.features = data_col
            headers = numpy.genfromtxt(data_csv_path, delimiter=',', max_rows=1, names=True)
            use_columns = [i for i, x in enumerate(headers.dtype.names) if x in data_col]
            loaded_data = numpy.genfromtxt(data_csv_path, delimiter=',', skip_header=1, usecols=use_columns)
        else:
            loaded_data = numpy.genfromtxt(data_csv_path, delimiter=',', skip_header=1)
        print(f">> Data loaded from {data_csv_path} with shape {loaded_data.shape}")
        # Load time
        loaded_time = numpy.genfromtxt(data_csv_path, delimiter=',', skip_header=1, usecols=[headers.dtype.names.index('icmT')])
        loaded_time = loaded_time.reshape(-1, 1)
        
        # Load labels
        loaded_labels = numpy.genfromtxt(labels_csv_path, delimiter=',', names=True)[label_type]
        
        # Handle cases where labels are in a single column but read as 1D
        if loaded_labels.ndim == 1:
            # Reshape the array into 1 column and as many rows as necessary
            # Note: For Reshape(-1, 1), the result is (n, ) -> (n, 1)
            # Note: For Reshape(1, -1), the result is (n, ) -> (1, n)
            loaded_labels = loaded_labels.reshape(-1, 1)
        
        print(f">> Labels loaded from {labels_csv_path} with shape {loaded_labels.shape}")

        # Ensure that the number of rows in data and labels match
        if loaded_data.shape[0] != loaded_labels.shape[0]:
            raise ValueError("The number of rows in data and labels must match.")
        
        # The batches
        self.batches_data.append(loaded_data)
        self.batches_label.append(loaded_labels)
        self.batches_time.append(loaded_time)
        
    def create_time_series(self):
        self.windowed_X = None
        self.windowed_y = None
        self.windowed_t = None
        
        for data, label, timestamp in zip(self.batches_data, self.batches_label, self.batches_time):
            num_rows = data.shape[0]
            num_channels = data.shape[1]
            
            if self.windowed_X is None or self.windowed_y is None or self.windowed_t is None:
                self.windowed_X = numpy.empty((0, num_channels), dtype=float)
                self.windowed_y = numpy.empty((0, label.shape[1]), dtype=int)
                self.windowed_t = numpy.empty((0, 1), dtype=float)
            
            if self.windowed_t.shape[0]:
                timestamp += self.windowed_t[-1, 0]
            
            self.windowed_X = numpy.concatenate((self.windowed_X, data), axis=0)
            self.windowed_y = numpy.concatenate((self.windowed_y, label), axis=0)
            self.windowed_t = numpy.concatenate((self.windowed_t, timestamp), axis=0)
        
    def create_windowed_inputs(self, window_size, step_size):
        """
        Creates windowed inputs and corresponding labels from the entire dataset.
        Each input includes N data points before and after the target point for each channel.
        :param window_size: Number of data points before and after the current point.
        """
        self.windowed_X = None
        self.windowed_y = None
        self.windowed_t = None

        print(f'>> Window size for each timestep: {window_size}')
        
        for data, label, timestamp in zip(self.batches_data, self.batches_label, self.batches_time):
            num_rows = data.shape[0]
            num_channels = data.shape[1]

            if window_size < 0 or step_size < 0:
                raise ValueError("window_size or step_size must be non-negative.")

            # Calculate the number of windowed samples
            num_windows = (num_rows - window_size) // step_size + 1
            if num_windows <= 0:
                raise ValueError("Not enough data points for the specified window_size.")

            # Preallocate arrays for efficiency
            loaded_windowed_X = numpy.zeros((num_windows, window_size, num_channels))
            loaded_windowed_y = numpy.zeros((num_windows, label.shape[1]))
            loaded_windowed_t = numpy.zeros((num_windows, 1))

            for i in range(num_windows):
                # Get the start and end indices of the sliding window
                start = i * step_size
                end = i * step_size + window_size
                # Input data is the sliding window
                loaded_windowed_X[i] = data[start : end]
                # Label and timestamp would be the middle of the sliding window
                # In case window size is one, numpy.floor would let the value be at the start index
                loaded_windowed_y[i] = label[int(start + numpy.floor((end - start) / 2))]
                loaded_windowed_t[i] = timestamp[int(start + numpy.floor((end - start) / 2))]
                    
            if self.windowed_X is None or self.windowed_y is None or self.windowed_t is None:
                self.windowed_X = numpy.empty((0, window_size, num_channels), dtype=float)
                self.windowed_y = numpy.empty((0, label.shape[1]), dtype=int)
                self.windowed_t = numpy.empty((0, 1), dtype=float)
            
            self.windowed_X = numpy.concatenate((self.windowed_X, loaded_windowed_X), axis=0)
            self.windowed_y = numpy.concatenate((self.windowed_y, loaded_windowed_y), axis=0)
            self.windowed_t = numpy.concatenate((self.windowed_t, loaded_windowed_t), axis=0)

    def shuffle_data(self):
        """
        Shuffles the windowed data and labels together to randomize the training and testing samples.
        (Not included time channel)
        """
        if self.windowed_X is None or self.windowed_y is None:
            raise ValueError("Windowed data not prepared. Call create_windowed_inputs() first.")

        # Use sklearn's shuffle to shuffle X and y in unison
        self.windowed_X, self.windowed_y = sklearn_shuffle(
            self.windowed_X, self.windowed_y, random_state=self.random_state
        )

    def split_data(self, test_ratio):
        """
        Splits the windowed data into training and testing sets.
        Assumes that shuffle_data() has been called if shuffling is desired.
        (Not included time channel)
        """
        if self.windowed_X is None or self.windowed_y is None:
            raise ValueError("Windowed data not prepared. Call create_windowed_inputs() first.")

        if self.windowed_X.shape[0] == 0:
            raise ValueError("No windowed data to split.")

        split_idx = int(self.windowed_X.shape[0] * (1.0 - test_ratio))

        self.X_train = self.windowed_X[:split_idx]
        self.y_train = self.windowed_y[:split_idx]
        self.X_test = self.windowed_X[split_idx:]
        self.y_test = self.windowed_y[split_idx:]

    def get_standardization_parameters(self):
        """
        Applies z-score normalization to specified columns based on the training data.
        The mean and standard deviation are computed from the training set and applied
        to both training and testing sets.
        """
        
        for i, ch in enumerate(self.features):
            # Extract the column data across all timesteps and samples in the training set
            train_col_data = self.X_train[..., i].flatten()
            mean = train_col_data.mean()
            std = train_col_data.std()
            if std == 0:
                raise ValueError(f"Standard deviation for column index #{i} {ch} is zero. Cannot standardize.")

            self.means[ch] = mean
            self.stds[ch] = std
            
    def apply_standardization_parameters(self):
        """
        Applies z-score normalization to specified columns based on the data.
        The mean and standard deviation are computed from the training set and applied
        to both training and testing sets.
        """
        
        for i, ch in enumerate(self.features):
            # Get the standardized mean and std for each feature
            mean = self.means[ch]
            std = self.stds[ch]
            
            # Apply standardization to testing sets
            self.X_train[..., i] = (self.X_train[..., i] - mean) / std
            self.X_test[..., i] = (self.X_test[..., i] - mean) / std
            
            print(f">> Standardized column #{i} {ch}: mean={self.means[ch]:.4f}, std={self.stds[ch]:.4f}")
    
    def import_standardized_parameters(self, path):
        # Prepare a named array to store the standardized parameters
        params = numpy.genfromtxt(path, delimiter=',', names=True, dtype=None)
        for param in params:
            self.means[str(param['channel'], 'utf-8')] = param['mean']
            self.stds[str(param['channel'], 'utf-8')] = param['std']
            
    def export_standardized_parameters(self, path):
        # Prepare a named array to store the standardized parameters
        params = numpy.zeros(len(self.features), dtype=[('channel', 'U10'), ('mean', float), ('std', float)])
        for i, ch in enumerate(self.features):
            params['channel'][i] = ch
            params['mean'][i] = self.means[ch]
            params['std'][i] = self.stds[ch]
        
        # Save the parameters to CSV file
        numpy.savetxt(path, params, delimiter=',', header=','.join(params.dtype.names), fmt='%s,%1.8f,%1.8f', comments='')

    def get_datasets(self):
        """Returns the prepared training and testing datasets."""
        return self.X_train, self.y_train, self.X_test, self.y_test
    
    
if __name__ == '__main__':
    window_size = 200
    step_size = 1
    test_ratio = 0.2  # 20% test data
    random_state = 42

    data_preparer = DataPreparer(
        test_ratio=test_ratio,
        random_state=random_state,
    )

    for i, f in enumerate(['data_20250203073445_dumbbell_exercise']):
        print(f'{i+1} ------------------')
        print(f'>> Data Preparation to split dataset into train and test')
        
        data_csv_path = os.path.join('data', f, 'icm_normalized.csv')
        labels_csv_path = os.path.join('data', f, 'label.csv')
        data_preparer.load_data(data_csv_path, labels_csv_path, label_type='label', data_col=['pitch_s', 'pitch_c'])
    
    print(f'OK ------------------')
    data_preparer.create_windowed_inputs(window_size, step_size, get_labels_start_stop=False)
    print(f">> Included windowed input X with shape: {data_preparer.windowed_X.shape}, labels y with shape: {data_preparer.windowed_y.shape}")
    data_preparer.shuffle_data()
    print(f">> Shuffled the windowed data and labels.")
    data_preparer.split_data()
    print(f'  Train X: {data_preparer.X_train.shape},\t Test X: {data_preparer.X_test.shape}')
    print(f'  Train Y: {data_preparer.y_train.shape},\t Test Y: {data_preparer.y_test.shape}')
    data_preparer.standardize()
    for i, ch in enumerate(['pitch_s', 'pitch_c']):
        print(f">> Standardizing column #{i} {ch}: mean={data_preparer.means[i]:.4f}, std={data_preparer.stds[i]:.4f}")
    
    X_train, y_train, X_test, y_test = data_preparer.get_datasets()

    print(f"  Training features shape: {X_train.shape}")  # Expected: (num_samples - 2N - test_ratio*...), e.g., (996, 5, 3)
    print(f"  Training labels shape: {y_train.shape}")    # Expected: (996, 1)
    print(f"  Testing features shape: {X_test.shape}")    # Expected: (~200, 5, 3)
    print(f"  Testing labels shape: {y_test.shape}")      # Expected: (~200, 1)
