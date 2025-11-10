import numpy as np

def sliding_window(data, window_size, step_size):
    print((len(data) - window_size) // step_size + 1)
    return [data[i:i + window_size] for i in range(0, len(data) - window_size + 1, step_size)]

# Example usage:
time_series_data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, ])
window_size = 4
step_size = window_size // 2


windows = sliding_window(time_series_data, window_size, step_size)
print(windows)