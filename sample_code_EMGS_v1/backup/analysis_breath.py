import argparse
import traceback
import numpy
import pywt
import os

import run

from matplotlib import pyplot
from scipy.signal import welch
from Toolbox import of_Math


class Dataset(run.Data):
    def __init__(self, data, skip_filter=False):
        super().__init__(data, skip_filter)
        
    def get_frequency_domain(self, start=0, period=2000):
        # Timestamp at which index
        t_start_emg = numpy.where(self.emg['emgT'] == start)[0][0]
        t_end_emg = numpy.where(self.emg['emgT'] == start+period)[0][0]
        
        # Get the signal in time domain
        emg_time = self.emg['emgT'][t_start_emg:t_end_emg]
        emg_signal = self.emg['emg'][t_start_emg:t_end_emg]
        
        # Get the signal in frequency domain
        frequencies, power_spectrum = welch(emg_signal, fs=1000)
        
        # Compute the MNF of the EMG
        mean_frequency = numpy.sum(power_spectrum * frequencies) / numpy.sum(power_spectrum)
        
        # Calculate the cumulative sum of the power spectrum
        cumulative_power = numpy.cumsum(power_spectrum)
        # Find the median frequency
        total_power = cumulative_power[-1]
        median_freq_index = numpy.where(cumulative_power >= total_power / 2)[0][0]
        median_frequency = frequencies[median_freq_index]
        
        # Calculate the root mean square
        root_mean_square = numpy.sqrt(numpy.mean(emg_signal ** 2))
        
        return frequencies, power_spectrum
        
    def get_frequency_map(self, start=0, end=None, period=2000):
        # Configure the time range of frequency map
        if end is None:        
            end = int(self.emg['emgT'][-1] - period)
        
        # Get the size of the power spectrum
        frequencies, power_spectrum = self.get_frequency_domain(start=0, period=period)
        n_freq = frequencies.shape[0]
        
        # Prepare a matrix to save frequency map
        freq_map = numpy.empty((0, n_freq))
        # Save frequency map for each time point
        for i in range(start, end):
            
            try:
                # Perform FFT for each time frame
                frequencies, power_spectrum = self.get_frequency_domain(start=i, period=period)
                freq_map = numpy.vstack((freq_map, power_spectrum))
                
            except IndexError:
                # Skip a time point if it has missing data
                freq_map = numpy.vstack((freq_map, numpy.zeros(n_freq)))
                
            print(i, end='\r')
        
        print()
        
        with open(os.path.join(self.path, 'freq_map.data'), 'wb') as f:
            numpy.save(f, freq_map)
        
        fig, ax = pyplot.subplots(2, 1, sharex=False, num='Display All')
        
        # EMG in Time Domain
        n = 0
        ax[n].plot(self.emg['emgT'][start:end], self.emg['emg'][start:end])
        ax[n].set_ylabel('EMG (mV)')
        ax[n].set_xlabel('Time (ms)')
        ax[n].set_title('Electromyography (EMG), Time Domain')
        ax[n].grid(True, which='both', axis='both')
        
        # EMG in Frequency Domain
        n += 1        
        ax[n].imshow(freq_map.T, aspect='auto', cmap='viridis', origin='lower')
        ax[n].set_ylabel('Frequency (Hz)')
        ax[n].set_xlabel('Time (ms)')
        ax[n].set_title('Electromyography (EMG) Frequency Map')
        ax[n].grid(True, which='both', axis='both')
        
        pyplot.tight_layout()
        pyplot.show()
        
    def cwt(self, wavelet, start=0, end=None, period=None):
        # Configure the time range of frequency map
        if end is None:        
            if period is None:
                end = int(self.emg['emgT'][-1])
            else:
                end = int(start + period)
        
        # Perform Continuous Wavelet Transform (CWT)
        # wavelet = 'cmor'      # 'cmor' is a complex Morlet wavelet
        data = self.emg['emg'][start: end]
        scales = numpy.arange(1, 128)
        coefficients, frequencies = pywt.cwt(data, scales, wavelet)

        # Plot the original signal
        pyplot.figure(figsize=(12, 8))
        
        pyplot.subplot(3, 1, 1)
        pyplot.plot(data)
        pyplot.title("Original Signal")
        pyplot.xlabel("Time (ms)")
        pyplot.ylabel("Amplitude")

        # Plot the wavelet coefficients at different scales (frequency bands)
        pyplot.subplot(3, 1, 2)
        pyplot.imshow(numpy.abs(coefficients), extent=[0, 1, 1, 128], cmap='jet', aspect='auto',
                      vmax=numpy.max(numpy.abs(coefficients)), vmin=0, origin='lower')
        pyplot.title("Wavelet Coefficients")
        pyplot.xlabel("Time (ms)")
        pyplot.ylabel("Scales")

        # Optionally, plot specific frequency bands using subplots
        # Example: Plotting for specific scales, e.g., 10, 20, 30
        pyplot.subplot(3, 1, 3)
        for scale in [10, 20, 30]:
            pyplot.plot(numpy.abs(coefficients[scale, :]), label=f'Scale {scale}')
        pyplot.title("Specific Frequency Bands")
        pyplot.xlabel("Time (ms)")
        pyplot.ylabel("Amplitude")
        pyplot.legend()

        pyplot.tight_layout()
        pyplot.show()
        
    def dwt_vs_hpf(self, wavelet, cutoff, level, start=0, end=None, period=None):
        # Configure the time range of frequency map
        if end is None:        
            if period is None:
                end = int(self.emg['emgT'][-1])
            else:
                end = int(start + period)
                
        if type(cutoff) in [list, tuple] and len(cutoff) >= 2:
            cutoff_lo = cutoff[0]
            cutoff_hi = cutoff[1]
        else:
            cutoff_lo = cutoff
            cutoff_hi = cutoff
        
        data = self.emg['emg'][start: end]
        
        # Perform discrete wavelet transform (DWT)
        
        # wavelet = 'db4'      # Daubechies wavelet
        # wavelet = 'sym4'     # Simlets wavelet
        # level = 10           # Decomposition level
        
        # Identify scales corresponding to EMG
        # EMG signals typically have higher frequency components compared to ECG
        # Assuming scales 1-5 capture ECG features (adjust based on signal characteristics)
        scales = numpy.arange(1, level + 1)
        ecg_scales = scales[:-3]
        emg_scales = scales[-2:]
        
        # Coefficient after wavelet transform
        coeffs = pywt.wavedec(data, wavelet=wavelet, mode='per', level=level)
        
        # # Plot wavelet coefficients for each scale
        # for i in range(level):
        #     pyplot.subplot(level + 3, 1, 2 + i)
        #     pyplot.plot(coeffs[level - i])
        #     pyplot.title(f"Wavelet Coefficients at Scale 2^{i + 1}")
        #     if i == 5:
        #         pyplot.xlabel("Samples")
        #         pyplot.ylabel("Coefficient Value")
                
        # Reconstruct the EMG signal from selected scales
        reconstructed_ecg = pywt.waverec([coeffs[0]] + [coeffs[i] if i in ecg_scales else numpy.zeros_like(coeffs[i]) for i in range(1, len(coeffs))], wavelet, mode='per')
        reconstructed_emg = pywt.waverec([coeffs[0]] + [coeffs[i] if i in emg_scales else numpy.zeros_like(coeffs[i]) for i in range(1, len(coeffs))], wavelet, mode='per')
        
        # Perform 2nd order Butterworth filter
        
        sample_freq = 1000
        
        lp_filter = of_Math.Butterworth()
        lp_filter.butter(sample_freq, cutoff=cutoff_lo, mode='low')
        
        hp_filter = of_Math.Butterworth()
        hp_filter.butter(sample_freq, cutoff=cutoff_hi, mode='high')
        
        filter_emg = hp_filter.filt(data)
        filter_ecg = lp_filter.filt(data)
        
        # Plot figures
        
        pyplot.figure(figsize=(12, 8))
        
        # Plot the mixed signal
        ax = pyplot.subplot(5, 1, 1)
        pyplot.plot(data)
        pyplot.title("Mixed Signal (ECG + EMG)")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # Plot the reconstructed ECG signal
        pyplot.subplot(5, 1, 2, sharex=ax)
        pyplot.plot(reconstructed_ecg)
        pyplot.title("Isolated ECG Signal by DWT")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")

        # Plot the lowpass filtered ECG signal
        pyplot.subplot(5, 1, 3, sharex=ax)
        pyplot.plot(filter_ecg)
        pyplot.title("Isolated ECG Signal by Lowpass filter")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # Plot the reconstructed EMG signal
        pyplot.subplot(5, 1, 4, sharex=ax)
        pyplot.plot(reconstructed_emg)
        pyplot.title("Isolated EMG Signal by DWT")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # Plot the highpass filtered EMG signal
        pyplot.subplot(5, 1, 5, sharex=ax)
        pyplot.plot(filter_emg)
        pyplot.title("Isolated EMG Signal by Highpass filter")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # pyplot.tight_layout()
        pyplot.show()
        
    def dwt_fft(self, wavelet, level, start=0, end=None, period=None):
        # Configure the time range of frequency map
        if end is None:        
            if period is None:
                end = int(self.emg['emgT'][-1])
            else:
                end = int(start + period)
                
        data = self.emg['emg'][start: end]

        # Perform discrete wavelet transform (DWT)
        
        # wavelet = 'db4'      # Daubechies wavelet
        # wavelet = 'sym4'     # Simlets wavelet
        # level = 10           # Decomposition level
        
        # Identify scales corresponding to EMG
        # EMG signals typically have higher frequency components compared to ECG
        # Assuming scales 1-5 capture ECG features (adjust based on signal characteristics)
        scales = numpy.arange(1, level + 1)
        ecg_scales = scales[:-3]
        emg_scales = scales[-2:]
        
        # Coefficient after wavelet transform
        coeffs = pywt.wavedec(data, wavelet=wavelet, mode='per', level=level)
        
        # # Plot wavelet coefficients for each scale
        # for i in range(level):
        #     pyplot.subplot(level + 3, 1, 2 + i)
        #     pyplot.plot(coeffs[level - i])
        #     pyplot.title(f"Wavelet Coefficients at Scale 2^{i + 1}")
        #     if i == 5:
        #         pyplot.xlabel("Samples")
        #         pyplot.ylabel("Coefficient Value")
                
        # Reconstruct the EMG signal from selected scales
        reconstructed_ecg = pywt.waverec([coeffs[0]] + [coeffs[i] if i in ecg_scales else numpy.zeros_like(coeffs[i]) for i in range(1, len(coeffs))], wavelet, mode='per')
        reconstructed_emg = pywt.waverec([coeffs[0]] + [coeffs[i] if i in emg_scales else numpy.zeros_like(coeffs[i]) for i in range(1, len(coeffs))], wavelet, mode='per')
        
        # Plot figures
        
        pyplot.figure(figsize=(12, 8))
        
        # Plot the mixed signal
        ax1 = pyplot.subplot(5, 1, 1)
        pyplot.plot(data)
        pyplot.title("Mixed Signal (ECG + EMG)")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # Plot the reconstructed ECG signal
        pyplot.subplot(5, 1, 2, sharex=ax1, sharey=ax1)
        pyplot.plot(reconstructed_ecg)
        pyplot.title("Isolated ECG Signal by DWT")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        # Plot the reconstructed EMG signal
        pyplot.subplot(5, 1, 3, sharex=ax1, sharey=ax1)
        pyplot.plot(reconstructed_emg)
        pyplot.title("Isolated EMG Signal by DWT")
        pyplot.xlabel("Samples")
        pyplot.ylabel("Amplitude")
        
        power_spectrum = numpy.abs(numpy.fft.fft(reconstructed_ecg)) ** 2
        
        half_length = len(power_spectrum) // 2
        frequencies = numpy.fft.fftfreq(2000, 1/1000)[1:half_length]
        power_spectrum = power_spectrum[1:half_length]
        
        # Plot the lowpass filtered ECG signal
        ax2 = pyplot.subplot(5, 1, 4)
        pyplot.plot(frequencies, power_spectrum)
        pyplot.title("Frequency Domain (ECG)")
        pyplot.xlabel("Frequency (Hz)")
        pyplot.ylabel("Amplitude")
        
        power_spectrum = numpy.abs(numpy.fft.fft(reconstructed_emg)) ** 2
        
        half_length = len(power_spectrum) // 2
        frequencies = numpy.fft.fftfreq(2000, 1/1000)[1:half_length]
        power_spectrum = power_spectrum[1:half_length]
        
        # Plot the highpass filtered EMG signal
        pyplot.subplot(5, 1, 5, sharex=ax2, sharey=ax2)
        pyplot.plot(frequencies, power_spectrum)
        pyplot.title("Frequency Domain (EMG)")
        pyplot.xlabel("Frequency (Hz)")
        pyplot.ylabel("Amplitude")
        
        # pyplot.tight_layout()
        pyplot.show()
        

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
    data = Dataset(buffer, skip_filter=True)
    data.set_path(args['path'])
    
    # data.get_frequency_domain(start=10000)      # ECG Only
    # data.get_frequency_domain(start=23000)      # ECG + EMG
    
    # data.get_frequency_map()

    # data.cwt('cmor')
    
    # data.dwt_vs_hpf(wavelet='sym4', level=10, cutoff=(30, 60))

    # data.dwt_fft(wavelet='sym4', level=10, start=10000, period=2000)    # ECG Only
    # data.dwt_fft(wavelet='sym4', level=10, start=23000, period=2000)    # ECG + EMG
    