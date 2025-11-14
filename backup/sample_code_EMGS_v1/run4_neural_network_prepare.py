import tensorflow
import json
import numpy
import os

from matplotlib import pyplot
from pytorch_tcn import TCN


class CustomNeuralNetwork:
    def __init__(self, 
                 input_shape=None, 
                 output_units=None, 
                 hidden_layers=[64, 64], 
                 activation='relu', 
                 output_activation='softmax',
                 model_type='dense',  # 'dense', 'rnn', 'tcn'
                 rnn_units=[64, 64], # List specifying units for each RNN layer
                 tcn_layers=3,        # Number of TCN layers
                 tcn_filters=64,      # Filters for TCN layers
                 tcn_kernel_size=3,   # Kernel size for TCN layers
                 optimizer='adam', 
                 loss='categorical_crossentropy', 
                 metrics=['accuracy'],
                 random_state=42):
        """
        Initializes the neural network with the given architecture.

        :param input_shape: Tuple representing the shape of the input data 
                            (timesteps, features) for RNN/TCN or (features,) for Dense.
        :param output_units: Number of units in the output layer.
        :param hidden_layers: List containing the number of units in each hidden layer 
                              (used differently based on model_type).
        :param activation: Activation function for hidden layers.
        :param output_activation: Activation function for the output layer.
        :param model_type: Type of model to build: 'dense', 'rnn', or 'tcn'.
        :param rnn_units: List specifying number of units for each RNN layer.
        :param tcn_layers: Number of TCN layers.
        :param tcn_filters: Number of filters in TCN layers.
        :param tcn_kernel_size: Kernel size for TCN layers.
        :param optimizer: Optimizer to compile the model.
        :param loss: Loss function to compile the model.
        :param metrics: List of metrics to compile the model.
        """
        self.input_shape = input_shape
        self.output_units = output_units
        self.hidden_layers = hidden_layers
        self.activation = activation
        self.output_activation = output_activation
        self.model_type = model_type.lower()
        self.rnn_units = rnn_units
        self.tcn_layers = tcn_layers
        self.tcn_filters = tcn_filters
        self.tcn_kernel_size = tcn_kernel_size
        self.optimizer = optimizer
        self.loss = loss
        self.metrics = metrics
        self.random_state = random_state
        self.history = None
        
        tensorflow.config.experimental.enable_op_determinism()
        tensorflow.random.set_seed(self.random_state)
        
        self.model = self.build_model()

    def build_model(self):
        """Builds the Keras model based on the specified architecture."""
        if self.model_type == 'dense':
            return self.build_dense_model()
        elif self.model_type == 'rnn':
            return self.build_rnn_model()
        elif self.model_type == 'tcn':
            return self.build_tcn_model()
        else:
            raise ValueError("Unsupported model_type. Choose from 'dense', 'rnn', or 'tcn'.")

    def build_dense_model(self):
        """Builds a standard Dense neural network."""
        model = tensorflow.keras.models.Sequential()
        model.add(tensorflow.keras.layers.InputLayer(shape=self.input_shape))

        # Flatten the input if it's 3D (e.g., from RNN/TCN data)
        if len(self.input_shape) > 1:
            model.add(tensorflow.keras.layers.Flatten())

        # Add hidden layers
        for idx, units in enumerate(self.hidden_layers):
            model.add(tensorflow.keras.layers.Dense(units, activation=self.activation, name=f"Dense_{idx+1}", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Add output layer
        model.add(tensorflow.keras.layers.Dense(self.output_units, activation=self.output_activation, name="Output_Layer", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Compile the model
        model.compile(optimizer=self.optimizer,
                      loss=self.loss,
                      metrics=self.metrics)
        return model

    def build_rnn_model(self):
        """Builds a Recurrent Neural Network (e.g., LSTM) model."""
        model = tensorflow.keras.models.Sequential()
        model.add(tensorflow.keras.layers.InputLayer(shape=self.input_shape))

        # Add RNN layers
        for idx, units in enumerate(self.rnn_units[:-1]):
            model.add(tensorflow.keras.layers.LSTM(units, activation='tanh', return_sequences=True, name=f"LSTM_{idx+1}", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Add the last RNN layer without return_sequences
        model.add(tensorflow.keras.layers.LSTM(self.rnn_units[-1], activation='tanh', name=f"LSTM_{len(self.rnn_units)}", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Add output layer
        model.add(tensorflow.keras.layers.Dense(self.output_units, activation=self.output_activation, name="Output_Layer", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Compile the model
        model.compile(optimizer=self.optimizer,
                      loss=self.loss,
                      metrics=self.metrics)
        return model

    def build_tcn_model(self):
        """Builds a Temporal Convolutional Network (TCN) model."""

        model = tensorflow.keras.models.Sequential()
        model.add(tensorflow.keras.layers.InputLayer(shape=self.input_shape))

        # Add TCN layers
        for i in range(self.tcn_layers):
            model.add(TCN(nb_filters=self.tcn_filters,
                         kernel_size=self.tcn_kernel_size,
                         dilations=[2**j for j in range(self.tcn_layers)],
                         activation=self.activation,
                         name=f"TCN_{i+1}",
                         kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Add output layer
        model.add(tensorflow.keras.layers.Dense(self.output_units, activation=self.output_activation, name="Output_Layer", kernel_initializer=tensorflow.keras.initializers.GlorotUniform(seed=self.random_state)))

        # Compile the model
        model.compile(optimizer=self.optimizer,
                      loss=self.loss,
                      metrics=self.metrics)
        return model

    def train(self, X_train, y_train, X_val=None, y_val=None, epochs=10, batch_size=32, verbose=1):
        """
        Trains the model on the provided training data.

        :param X_train: Training data features.
        :param y_train: Training data labels.
        :param X_val: Validation data features.
        :param y_val: Validation data labels.
        :param epochs: Number of training epochs.
        :param batch_size: Batch size for training.
        :param verbose: Verbosity mode.
        :return: History object containing training details.
        """
        if X_val is not None and y_val is not None:
            self.history = self.model.fit(X_train, y_train,
                                          validation_data=(X_val, y_val),
                                          epochs=epochs,
                                          batch_size=batch_size,
                                          verbose=verbose)
        else:
            self.history = self.model.fit(X_train, y_train,
                                          epochs=epochs,
                                          batch_size=batch_size,
                                          verbose=verbose)
        return self.history

    def evaluate(self, X_test, y_test, verbose=1):
        """
        Evaluates the model on the test data.

        :param X_test: Test data features.
        :param y_test: Test data labels.
        :param verbose: Verbosity mode.
        :return: Evaluation metrics.
        """
        return self.model.evaluate(X_test, y_test, verbose=verbose)

    def plot_metrics(self, path):
        """
        Plots training and validation metrics (loss and accuracy) if history is available.
        """
        if self.history is None:
            print(">> No training history available. Train the model first.")
            return

        # Plot Loss
        pyplot.figure(figsize=(12, 5))

        pyplot.subplot(1, 2, 1)
        pyplot.plot(self.history.history.get('loss'), label='Training Loss')
        if 'val_loss' in self.history.history:
            pyplot.plot(self.history.history.get('val_loss'), label='Validation Loss')
        pyplot.title('Loss Over Epochs')
        pyplot.xlabel('Epoch')
        pyplot.ylabel('Loss')
        pyplot.legend()

        # Plot Accuracy
        if 'accuracy' in self.history.history or 'acc' in self.history.history:
            pyplot.subplot(1, 2, 2)
            metrics_key = 'accuracy' if 'accuracy' in self.history.history else 'acc'
            pyplot.plot(self.history.history.get(metrics_key), label='Training Accuracy')
            if f'val_{metrics_key}' in self.history.history:
                pyplot.plot(self.history.history.get(f'val_{metrics_key}'), label='Validation Accuracy')
            pyplot.title('Accuracy Over Epochs')
            pyplot.xlabel('Epoch')
            pyplot.ylabel('Accuracy')
            pyplot.legend()

        pyplot.tight_layout()
        
        pyplot.savefig(path)
        
        pyplot.show()
        
    def export_trainable_parameters(self, path):
        self.model.save(path)
        
    def import_trainable_parameters(self, path):
        del self.model
        self.model = tensorflow.keras.models.load_model(path, compile=True)

    def save_parameters(self, filepath='trainable_params.json'):
        """
        Exports the trainable parameters of the model to a JSON file.

        :param filepath: Path to save the parameters.
        """
        # Ensure the directory exists
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        params = {}
        for layer in self.model.layers:
            # Check if the layer has weights
            if isinstance(layer, (tensorflow.keras.layers.Dense, tensorflow.keras.layers.LSTM)) or hasattr(layer, 'get_weights'):
                try:
                    weights = layer.get_weights()
                    if weights:
                        layer_params = {}
                        for i, weight in enumerate(weights):
                            layer_params[f'weight_{i}'] = weight.tolist()
                        params[layer.name] = layer_params
                except AttributeError:
                    continue  # Some layers like InputLayer may not have weights

        with open(filepath, 'w') as f:
            json.dump(params, f)
        print(f">> Trainable parameters exported to {filepath}")

    def load_parameters(self, filepath='trainable_params.json'):
        """
        Loads trainable parameters from a JSON file into the model.

        :param filepath: Path from where to load the parameters.
        """
        if not os.path.exists(filepath):
            print(f">>! File {filepath} does not exist.")
            return

        with open(filepath, 'r') as f:
            params = json.load(f)

        for layer in self.model.layers:
            if layer.name in params:
                layer_params = []
                # Assuming weights are stored in order
                sorted_keys = sorted(params[layer.name].keys(), key=lambda x: int(x.split('_')[1]))
                for key in sorted_keys:
                    array = numpy.array(params[layer.name][key])
                    layer_params.append(array)
                try:
                    layer.set_weights(layer_params)
                except ValueError as e:
                    print(f">>! Error setting weights for layer {layer.name}: {e}")
        print(f">> Trainable parameters loaded from {filepath}")

    def summary(self):
        """Prints the summary of the model."""
        self.model.summary()
        