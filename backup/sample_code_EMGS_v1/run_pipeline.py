import os
import numpy
import tensorflow

from matplotlib import pyplot

# Default setting
# please override these in the __main__ function
MODEL_ID = ''                   # Only be used to set folder name
MODEL = 'dense'                 # Select neural work model type
LABEL_TYPE = 'label'            # Which label column be used, default is 'label'

# Select which pipeline workflow will be executed
# please override these in the __main__ function
TO_PREPROCESSING = None         # For data processing and labelling
TO_TRAIN_MODEL = None           # For train model
TO_TEST_MODEL = None            # For test model
    
# Path to database and files
PATH_TO_DATABASE = os.path.join('D:/', 'Data', 'data')
LIST_OF_ALL_DATA = [x for x in os.listdir(PATH_TO_DATABASE) if x.startswith('data_')]

PATH_TO_MODEL = os.path.join(PATH_TO_DATABASE, 'model')     # Will append model id, e.g. /model_tcn_layer2

# Files generated in each DATA folder
CSV_FILE_DATA = 'icm_normalized.csv'
CSV_FILE_LABEL = 'label.csv'
PNG_LABEL = 'fig_labelled.png'
# Files generated in each MODEL folder
CSV_FILE_STANDARD = 'std.csv'
KERAS_SAVED_MODEL = 'model.keras'
PNG_MODEL_METRICS = 'fig_model.png'
PNG_MODEL_OUTPUT = 'fig_output.png'
TXT_DATASET_TRAIN = 'train.dataset'
TXT_DATASET_TEST = 'test.dataset'

# Setup environment parameters
WINDOW_SIZE = 200         # When setting the sliding window for neural work, how many cell before or after is included.
# STEP_SIZE = WINDOW_SIZE // 2 if WINDOW_SIZE > 1 else 1      # For sliding window, how many cell to shift for the next window
STEP_SIZE = 1
TEST_RATIO = 0.2        # Proportion of dataset including in test set
RANDOM_STATE = 42       # Seed for setting random number generator

# List of data column included in features of neural network
LIST_OF_USED_CHANNELS = [       
    # 'icmT',
    # 'accT',
    # 'accX',
    # 'accY',
    # 'accZ',
    # 'gyrT',
    # 'gyrX',
    # 'gyrY',
    # 'gyrZ',
    # 'magT',
    # 'magX',
    # 'magY',
    # 'magZ',
    # 'roll',
    # 'pitch',
    # 'yaw',
    'accX_',
    'accX_1',
    'accX_2',
    'accY_',
    'accY_1',
    'accY_2',
    'accZ_',
    'accZ_1',
    'accZ_2',
    'gyrX_',
    'gyrX_1',
    'gyrX_2',
    'gyrY_',
    'gyrY_1',
    'gyrY_2',
    'gyrZ_',
    'gyrZ_1',
    'gyrZ_2',
    'magX_',
    'magX_1',
    'magX_2',
    'magY_',
    'magY_1',
    'magY_2',
    'magZ_',
    'magZ_1',
    'magZ_2',
    # 'roll_',
    'roll_s',
    'roll_c',
    'roll_1',
    'roll_2',
    # 'pitch_',
    'pitch_s',
    'pitch_c',
    'pitch_1',
    'pitch_2',
    # 'yaw_',
    'yaw_s',
    'yaw_c',
    'yaw_1',
    'yaw_2',
]


def get_list_of_folder(model_id='', type='train'):
    """ Gather a list of dataset folder specified in plain text file """
    
    # Use specified model id folder
    path_to_model = PATH_TO_MODEL
    if model_id:
        path_to_model = f'{path_to_model}_{model_id}'
    
    # From the model folder, get a list of dataset based on type
    list_of_selected_dataset = []
    path_to_list_of_dataset = os.path.join(path_to_model, f'{type}.dataset')
    with open(path_to_list_of_dataset, 'r') as f:
        # The list of dataset folder name is simply stored in a plain text file per line
        for path_to_dataset in f.readlines():
            
            # Dataset can be skipped by adding a comment sign at the start of the line
            if path_to_dataset.startswith('#'):
                continue
            
            # Gather a list of dataset based on the type
            list_of_selected_dataset.append(path_to_dataset.strip('# \n'))
            
    return list_of_selected_dataset


def data_processing():
    """ For data processing (filtering, normalization, compute new features) """
    import run1_data_processing
    
    work = run1_data_processing.Operation()
    for i, f in enumerate(LIST_OF_ALL_DATA):
        print(f'{i+1} ------------------')
        print(f'>> Data Processing')
        fpath = os.path.join(PATH_TO_DATABASE, f)
        work.set_path(fpath)
        print(f'>> Data path: {fpath}')
        work.load_data_from_file()
        print(f'>> Data loading successfully. (ICM Data Size: {work.icm.shape})')
        work.process_data()
        print(f'>> Data processing successfully.')
        work.save_data(suffix='normalized')
        print(f'>> Data saved to csv file successfully.')
        
        
def data_labelling():
    """ For user to manually label/highlight class labels on pyplot data plotter """
    import run2_data_labelling
    
    work = run2_data_labelling.Operation()
    for i, f in enumerate(LIST_OF_ALL_DATA):
        print(f'{i+1} ------------------')
        print(f'>> Data Labelling')
        fpath = os.path.join(PATH_TO_DATABASE, f)
        work.set_path(fpath)
        print(f'>> Data path: {fpath}')
        work.load_label()
        work.load_data()
        print(f'>> Load data and labels successfully.')
        work.label_data(path_png=PNG_LABEL)
        print(f'>> Updated data labelling.')
        work.save_label()
        print(f'>> Save labels successfully.')
        
        
def data_window_split(dataset_type='train', model_id='', is_window=True, label_type='label'):
    """ For user to gather dataset with specific tensor structure """
    print(f'>> Working on Model ID: # {model_id}')
    print(f'>> Setting up data windows...')
    import run3_data_train_test_split
    
    path_to_model = PATH_TO_MODEL
    if model_id:
        path_to_model = f'{path_to_model}_{model_id}'
        
    # For preparing train dataset
    work = run3_data_train_test_split.DataPreparer(random_state=RANDOM_STATE)

    # Load all data file for a type of dataset (train? or test?)
    for i, f in enumerate(get_list_of_folder(model_id, type=dataset_type)):
        print(f'{i+1} ------------------')
        print(f'>> Data Preparation for {dataset_type} dataset')
        
        data_csv_path = os.path.join(PATH_TO_DATABASE, f, CSV_FILE_DATA)
        labels_csv_path = os.path.join(PATH_TO_DATABASE, f, CSV_FILE_LABEL)
        work.load_data(data_csv_path, labels_csv_path, label_type=label_type, data_col=LIST_OF_USED_CHANNELS)
    
    # Check if there are any data loaded
    print(f'OK ------------------')
    if len(work.batches_data) == 0:
        print(f'>> No data available.')
        return None
    
    # Whether sliding window is involved (Dense) or not (RNN, CNN, etc)
    if is_window:
        # Apply sliding window to the batched data
        work.create_windowed_inputs(WINDOW_SIZE, STEP_SIZE)
        print(f">> Included windowed input X with shape: {work.windowed_X.shape}, labels y with shape: {work.windowed_y.shape}")
    
    else:
        # Directly use the multivariate time series data. Batched data concatenate together
        work.create_time_series()
        print(f">> Included windowed input X with shape: {work.windowed_X.shape}, labels y with shape: {work.windowed_y.shape}")
    
    if dataset_type == 'train':
        # Training dataset will export standardized parameters

        if is_window:
            # Windowed features can shuffle dataset with no problem as each timesteps are independent
            print(f">> Shuffling the windowed data and labels.")
            work.shuffle_data()

            # After shuffle, sequence does not matter, can split data by proportion along length of dataset
            print(f">> Splitting the shuffled windowed data and labels.")
            work.split_data(TEST_RATIO)
        
        else:
            # Data timestep sequence matter in this case
            # I prefer not to validate the model, and to test model later
            work.split_data(0.0)
            
        print(f'  Train X: \t{work.X_train.shape},\tTrain Y: \t{work.y_train.shape}')
        print(f'  Test X: \t{work.X_test.shape},\tTest Y: \t{work.y_test.shape}')

        # Standardize dataset with train set
        # Apply and export standardized parameters
        print(f'>> Standardizing all the columns with z-score...')
        work.get_standardization_parameters()
        work.export_standardized_parameters(path=os.path.join(path_to_model, CSV_FILE_STANDARD))
        print(f'>> Exported standardized parameters to file.')
        
    elif dataset_type == 'test':
        # Testing data will import standardized parameters
        
        # Use all dataset as test, i.e., test ratio is one
        work.split_data(1.0)
        print(f'  Train X: \t{work.X_train.shape},\tTrain Y: \t{work.y_train.shape}')
        print(f'  Test X: \t{work.X_test.shape},\tTest Y: \t{work.y_test.shape}')

        # Import and apply standardized parameters
        work.import_standardized_parameters(path=os.path.join(path_to_model, CSV_FILE_STANDARD))
        print(f'>> Imported standardization parameters from file.')
    
    else:
        return None
    
    # Apply standardization parameters
    work.apply_standardization_parameters()
    print(f'>> Standardized all the columns with z-score...')
    
    # Get the train set and test set
    return work


def neural_network_prepare(dataset, model_id='', model='dense'):
    """ Setup the neural network model """
    
    print(f'>> Working on Model ID: # {model_id}')
    print(f'>> Setting up Neural Network...')
    import run4_neural_network_prepare
    
    path_to_model = PATH_TO_MODEL
    if model_id:
        path_to_model = f'{path_to_model}_{model_id}'
        
    # Get train and test dataset
    train_x, train_y, test_x, test_y = dataset
    
    # Flatten the timestep window and features
    train_x = tensorflow.constant(train_x)
    train_x = tensorflow.reshape(train_x, [train_x.shape[0], -1])
    test_x = tensorflow.constant(test_x)
    test_x = tensorflow.reshape(test_x, [test_x.shape[0], -1])
    
    # Print dataset characteristics
    num_channels = test_x.shape[1]
    num_classes = len(numpy.unique(test_y))
    print(f'>> Number of Features: {num_channels}')
    print(f'>> Number of Classes: {num_classes}')
    
    # Turn labels into One-Hot classes map
    train_y = tensorflow.constant(train_y)
    test_y = tensorflow.constant(test_y)
    train_y = tensorflow.keras.utils.to_categorical(train_y, num_classes)
    test_y = tensorflow.keras.utils.to_categorical(test_y, num_classes)
    
    # Set train and test dataset
    dataset = train_x, train_y, test_x, test_y
    
    # Initialize the custom neural network
    model = run4_neural_network_prepare.CustomNeuralNetwork(
        input_shape=(num_channels,),
        output_units=num_classes,
        # hidden_layers=[1024, 1024],
        hidden_layers=[256, 256],
        model_type=model,
        random_state=RANDOM_STATE,
    )

    # Print the model summary
    model.summary()
    
    return dataset, model


def neural_network_train(dataset, model):
    """ Train the neural network model """
    
    # Get train and test dataset
    train_x, train_y, test_x, test_y = dataset
    
    # Train the model
    history = model.train(
        train_x, train_y,
        epochs=10,
        verbose=2,
    )
    # Evaluate the model
    loss, accuracy = model.evaluate(
        test_x, test_y,
    )
    # Plot training metrics
    model.plot_metrics(path=os.path.join(path_to_model, PNG_MODEL_METRICS))
    
    # Export trainable parameters from the model
    model.export_trainable_parameters(path=os.path.join(path_to_model, KERAS_SAVED_MODEL))
    print(f'>> Exported trainable parameters of neural network to file.')
    
    return model
    
    
def neural_network_test(dataset, model):
    """ Test the neural network model """
    
    # Get train and test dataset
    _, _, test_x, test_y = dataset
    
    # Import trainable parameters to the model
    model.import_trainable_parameters(path=os.path.join(path_to_model, KERAS_SAVED_MODEL))
    print(f'>> Imported trainable parameters of neural network from file.')
    
    # --------------------------- SHOW TEST RESULTS
    # Show the output of the model with test dataset as input
    output = (model.model(test_x), test_y)
    
    return output
        

def neural_network_output(output, data):
    """ Plot the tested neural network model output """
    
    # Prepare feature map
    features = {}
    for i, ch in enumerate(LIST_OF_USED_CHANNELS):
        features[ch] = i
    
    # Setup plot
    print(f'>> Plot neural network outputs.')
    fig, ax = pyplot.subplots(8, 1, sharex=True, figsize=(12, 8))
    # Full screen
    mng = pyplot.get_current_fig_manager()
    mng.full_screen_toggle()
    # Draw subplots index #n
    n = 0
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['roll_s']]*90, color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['roll_c']]*90, color='r')
    ax[n].set_ylabel('roll_')
    n += 1
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['pitch_s']]*90, color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['pitch_c']]*90, color='r')
    ax[n].set_ylabel('pitch_')
    n += 1
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['yaw_s']]*90, color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['yaw_c']]*90, color='r')
    ax[n].set_ylabel('yaw_')
    n += 1
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['accX_']], color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['accY_']], color='r')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['accZ_']], color='g')
    ax[n].set_ylabel('accXYZ_')
    n += 1
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['gyrX_']], color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['gyrY_']], color='r')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['gyrZ_']], color='g')
    ax[n].set_ylabel('gyrXYZ_')
    n += 1
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['magX_']], color='b')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['magY_']], color='r')
    ax[n].plot(data.batches_time[0], data.batches_data[0][:, features['magZ_']], color='g')
    ax[n].set_ylabel('magXYZ_')
    n += 1
    ax[n].plot(data.windowed_t, numpy.argmax(output[0], axis=1))
    ax[n].set_ylabel('Predicated Label')
    n += 1
    ax[n].plot(data.windowed_t, numpy.argmax(output[1], axis=1))
    ax[n].set_ylabel('True Label')
    ax[n].set_xlabel('time (ms)')
    n += 1
    
    pyplot.tight_layout()
    
    pyplot.savefig(os.path.join(path_to_model, PNG_MODEL_OUTPUT))
    
    pyplot.show()


def neural_network_process(mode, model='dense'):
    """ Sub-pipeline workflow for working on neural network 
        - Prepare dataset tensors
        - Prepare neural work model
        - Train or test neural network model 
    """
    
    # Only Dense will be using sliding window
    # TCN and RNN will do classification per frame
    is_window = True if model == 'dense' else False
    
    # Data pre-processing to get dataset with appropriate tensor structure
    dataset = data_window_split(mode, MODEL_ID, is_window=is_window, label_type=LABEL_TYPE)
    
    if dataset is not None:
        # Get dataset
        raw_dataset = dataset.get_datasets()
        
        # Prepare the neural network model
        processed_dataset, model = neural_network_prepare(raw_dataset, MODEL_ID, model)
        
        # Apply the neural network model
        if mode == 'train':
            # Return the trained model
            neural_network_train(processed_dataset, model)
        
        elif mode == 'test':
            # Return the tested output of the model
            output = neural_network_test(processed_dataset, model)
            neural_network_output(output, dataset)
            
    
if __name__ == '__main__':
    
    """ Select model and label """
    LABEL_TYPE = 'step'
    # MODEL_ID = 'steps_per_window10_step1_node1024'
    # MODEL = 'dense'
    MODEL_ID = 'steps_tcn'
    MODEL = 'tcn'
    
    """ Select which pipeline workflow will be executed """
    # TO_PREPROCESSING = True
    TO_TRAIN_MODEL = True
    TO_TEST_MODEL = True
    
    """ Prepare the model folder """
    # Prepare the model folder with specfied id
    path_to_model = PATH_TO_MODEL
    if MODEL_ID:
        path_to_model = f'{path_to_model}_{MODEL_ID}'
    
    if not os.path.exists(path_to_model):
        # create a new one with empty dataset list if model folder not found
        os.mkdir(path_to_model)
        open(os.path.join(path_to_model, TXT_DATASET_TRAIN), 'w')
        open(os.path.join(path_to_model, TXT_DATASET_TEST), 'w')
    
    """ Run the Pipeline Workflow """
    
    if TO_PREPROCESSING:
        # Loop the test database for data pre-processing
        data_processing()
        data_labelling()
    
    if TO_TRAIN_MODEL:
        # Trained model will be exported to database
        neural_network_process(mode='train', model=MODEL)
        
    if TO_TEST_MODEL:
        # Tested model output will be displayed to user
        output = neural_network_process(mode='test', model=MODEL)
