import os
import numpy
import tensorflow

import run3_data_train_test_split
import run4_neural_network_prepare


X_train, y_train, X_test, y_test = data_preparer.get_datasets()


# Step 5: Encode Labels (One-Hot)
unique_labels = numpy.unique(y_train)
num_classes = unique_labels.shape[0]
label_mapping = {label: idx for idx, label in enumerate(unique_labels)}
y_train_mapped = numpy.array([label_mapping[label[0]] for label in y_train])
y_test_mapped = numpy.array([label_mapping[label[0]] for label in y_test])

y_train_encoded = tensorflow.keras.utils.to_categorical(y_train_mapped, num_classes=num_classes)
y_test_encoded = tensorflow.keras.utils.to_categorical(y_test_mapped, num_classes=num_classes)

# Step 6: Initialize and Train the Neural Network
input_shape = (X_train.shape[1], X_train.shape[2])  # (timesteps, features)
output_units = num_classes  # Number of classes

hidden_layers = [128, 64]  # Example hidden layers

# Initialize the CustomNeuralNetwork with RNN architecture
cnn_rnn = run4_neural_network_prepare.CustomNeuralNetwork(
    input_shape=input_shape,
    output_units=output_units,
    hidden_layers=hidden_layers,
    activation='tanh',             # Activation suitable for LSTM
    output_activation='softmax',   # For multi-class classification
    model_type='rnn',
    rnn_units=[128, 64],           # LSTM units
    optimizer='adam',
    loss='categorical_crossentropy',
    metrics=['accuracy']
)

# Print the model summary
cnn_rnn.summary()

# Train the model
history_rnn = cnn_rnn.train(
    X_train, 
    y_train_encoded, 
    X_val=X_test, 
    y_val=y_test_encoded, 
    epochs=20, 
    batch_size=32, 
    verbose=2
)

# Evaluate the model
loss_rnn, accuracy_rnn = cnn_rnn.evaluate(X_test, y_test_encoded, verbose=0)
print(f"RNN Test Loss: {loss_rnn:.4f}, Test Accuracy: {accuracy_rnn:.4f}")

# Plot training metrics
cnn_rnn.plot_metrics()

# Export trainable parameters
cnn_rnn.export_parameters('dummy_data/rnn_model_params.json')
