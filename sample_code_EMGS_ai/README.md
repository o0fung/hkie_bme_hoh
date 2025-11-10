# EMGS_AI: Electromyography Signal (EMGS) User Interface

## Overview

**EMGS_AI** is a user-friendly desktop application for connecting to Electromyography (EMG) devices via Bluetooth Low Energy (BLE), visualizing EMG data, and training machine learning models on the collected signals. The application is built with Python, using PyQt for the graphical interface and Bleak for BLE communication. It is designed for researchers, students, and hobbyists interested in biosignal processing and AI.

---

## Features

- **Bluetooth LE Device Scanning & Connection:**  
  Easily scan for nearby EMG devices and connect/disconnect with a click.

- **Live Data Visualization:**  
  View real-time EMG signals streamed from your device.

- **Machine Learning Integration:**  
  Train and test AI models on your EMG data directly from the app.

- **User-Friendly Interface:**  
  Intuitive controls for device management, data logging, and model training.

---

## Requirements

- **Operating System:** macOS, Windows, or Linux
- **Python:** 3.8 or newer (Python 3.13 tested)
- **Hardware:** BLE-compatible EMG device (e.g., Nordic UART Service-based)

### Python Dependencies

Install all dependencies using pip:

```bash
pip install -r requirements.txt
```

---

## Getting Started

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/o0fung/RR_EMG.git
   cd RR_EMG/EMGS_ai
   ```

2. **Install Dependencies:**

   Ensure you have Python 3.8+ and pip installed, then run:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application:**

   Launch the app with:

   ```bash
   python app.py
   ```

4. **Connect to an EMG Device:**

   - Turn on your EMG device and make it discoverable.
   - In the app, go to the **EMGS** page and select **Scan** to search for nearby EMG devices.
   - Choose your device from the list and select **Connect** to connect to the EMG devices.

5. **Visualize EMG Data:**

   - Once connected, navigate to the **Live Data** tab.
   - Observe the real-time EMG signal plots.

6. **Train a Machine Learning Model:**

   - Switch to the **Model Training** tab.
   - Select a dataset and choose your model parameters.
   - Click **Train Model** to start the training process.

---

## Troubleshooting

- **Connection Issues:**

  - Ensure your EMG device is powered on and in range.
  - Restart the app and try connecting again.

- **Data Not Updating:**

  - Check the USB connection of your EMG device.
  - Ensure no other application is using the COM port.

- **Model Training Errors:**

  - Verify your dataset is correctly formatted.
  - Check the console for specific error messages.

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch: `git checkout -b feature/YourFeature`
3. Make your changes and commit them: `git commit -m 'Add some feature'`
4. Push to the branch: `git push origin feature/YourFeature`
5. Open a pull request.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Inspired by the need for accessible EMG signal processing tools.
- Built using Python, PyQt, and Bleak with gratitude to their respective communities.

---

## Contact

For questions or feedback, please open an issue on GitHub or contact the maintainer at lf.yeung@rehab-robotics.com.hk

---

Enjoy exploring the world of EMG signals and machine learning with **EMGS_AI**!
