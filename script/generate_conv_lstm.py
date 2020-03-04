import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from tqdm import tqdm

from holt_winter import *
from TSClass_function import *
from TSClass_lorenz import *

import tensorflow as tf
from tensorflow.keras.models import Sequential, Model, load_model
from tensorflow.keras.layers import Dense, Activation, Conv2D, MaxPooling2D, Dropout, Flatten, LSTM, \
    GlobalAveragePooling2D, BatchNormalization, TimeDistributed, Input, Bidirectional
from tensorflow.keras.optimizers import RMSprop
from tensorflow.keras import regularizers

# %%---------------------------------------------------------------------------
'''
Functions and Classes:
    Write a class to test later
'''


# class forecaster:


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def function_creator(start_idx, end_idx, dt, sigma):
    """
    Example of callable object written the "correct way",
    that accepts as first arguments range of indexes [start_idx, end_idx)
    and return an array of (end_idx-start_idx,) values.
    In this case it is sin + noise
    """
    x1 = start_idx * dt
    x2 = (end_idx - 1) * dt

    m = 28 * dt
    x = np.linspace(x1, x2, end_idx - start_idx)

    return 70 + 15 * np.cos(2 * np.pi * x / (3.4 * m)) + 7 * np.sin(2 * np.pi * x / m) + np.random.normal(loc=0.0,
                                                                                                          scale=sigma,
                                                                                                          size=(
                                                                                                                      end_idx - start_idx))


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
def sequence_splitter(signal, inp_window, out_window):
    '''
    Split a signal into a X-Window and a Y-Window
    Returns:
        inp: input_window of shape(#samples,inp_window)
        out: output window of shape(#samples,out_window)
    The #samples is a function of the length of the signal, inp_window and out_window parameters.
    '''
    # Prepare windows to fill
    inp = list()
    out = list()

    for i in range(len(signal)):
        pointer_input = i + inp_window
        pointer_output = pointer_input + out_window

        if pointer_output > len(signal):
            break

        window_X = signal[i:pointer_input]
        window_Y = signal[pointer_input:pointer_output]

        inp.append(window_X)
        out.append(window_Y)

    return np.array(inp), np.array(out)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

def show_result(y, y_pred, full=False):
    plt.plot(y[150:750], c='red', lw=0.5)
    plt.plot(y_pred[150:750], c='blue')
    plt.show()

    if full == True:
        plt.plot(y, c='red')
        plt.plot(y_pred, c='blue')
        plt.show()
    # %%---------------------------------------------------------------------------


'''
Constants
'''
N_points = 100000

window_size_x = 100  # the x-window size
window_size_y = 100  # the y-window size

img_size = 32
sample_range = (-1, 1)
# %%---------------------------------------------------------------------------
'''
Create Dataset
'''

ts = TSC_lorenz(savevals=True)

time_series = ts.get_next_N_vals(N_points)

time_series_train = time_series[0:60000]
time_series_test = time_series[60000:N_points]

# %%---------------------------------------------------------------------------
'''
Train/Test, Normalize & Sequence split
'''

# Define Test/Train set

signal_train = time_series[0:60000].reshape(-1, 1)
signal_test = time_series[60000:N_points].reshape(-1, 1)

# Scaling
from sklearn.preprocessing import MinMaxScaler

MMscaler = MinMaxScaler(feature_range=sample_range)

signal_train_scaled = MMscaler.fit_transform(signal_train).flatten()
signal_test_scaled = MMscaler.fit_transform(signal_test).flatten()

# Split Sequence
window_input_train, window_output_train = sequence_splitter(signal_train_scaled, window_size_x, window_size_y)
window_input_test, window_output_test = sequence_splitter(signal_test_scaled, window_size_x, window_size_y)

# %%---------------------------------------------------------------------------
'''
Field transformations
'''
from pyts.image import GramianAngularField
from pyts.image import MarkovTransitionField

gadf = GramianAngularField(image_size=img_size, method='difference', sample_range=sample_range)
gasf = GramianAngularField(image_size=img_size, method='summation', sample_range=sample_range)
mtf = MarkovTransitionField(image_size=img_size, n_bins=8, strategy='quantile')

gadf_transformed_train = np.expand_dims(gadf.fit_transform(window_input_train), axis=3)
gasf_transformed_train = np.expand_dims(gasf.fit_transform(window_input_train), axis=3)
mtf_transformed_train = np.expand_dims(mtf.fit_transform(window_input_train), axis=3)

X_train_windowed = np.concatenate((gadf_transformed_train, gasf_transformed_train, mtf_transformed_train), axis=3)

gadf_transformed_test = np.expand_dims(gadf.fit_transform(window_input_test), axis=3)
gasf_transformed_test = np.expand_dims(gasf.fit_transform(window_input_test), axis=3)
mtf_transformed_test = np.expand_dims(mtf.fit_transform(window_input_test), axis=3)

X_test_windowed = np.concatenate((gadf_transformed_test, gasf_transformed_test, mtf_transformed_test), axis=3)

# %%---------------------------------------------------------------------------
# ****************************************************************************
'''
Neural Network - Field
'''
# ****************************************************************************

# %% Conv-MLP
# Constants
N_channels_Conv_MLP = 3
bsize = 32
epch = 2

# Data reshaping
X_train_Conv_MLP = X_train_windowed
y_train_Conv_MLP = window_output_train

X_test_Conv_MLP = X_test_windowed
y_test_Conv_MLP = window_output_test

# %%

# ===================CONV LSTM==================================

# Conv part
def get_base_model(img_size):
    inp = Input(shape=(img_size, img_size, 3))
    x = BatchNormalization()(inp)
    x = Conv2D(32, kernel_size=(4, 4), activation="elu", padding="same")(x)
    x = BatchNormalization()(x)
    x = Dropout(0.1)(x)
    # for i in range(3):
    #     x = Conv2D(64, kernel_size=(4,4), padding='same', activation='elu')(x)
    #     x = BatchNormalization()(x)
    #     x = MaxPooling2D(padding='same', pool_size=(2,2))(x)
    #     x = Dropout(0.1)(x)

    final = Conv2D(128, kernel_size=(5, 5), strides=5, activation="elu", padding="same")(x)
    final = BatchNormalization()(final)
    final = Dropout(0.1)(final)

    final = Flatten()(final)

    base_model = Model(inputs=inp, outputs=final)
    base_model.compile(optimizer="adam", loss="mse")
    base_model.summary()
    return base_model


# LSTM part
def get_model_lstm(window_size_y, img_size, seq_len):
    dropout = 0.4

    seq_input = Input(shape=(seq_len, img_size, img_size, 3))
    base_model = get_base_model(img_size)
    encoded_sequence = TimeDistributed(base_model)(seq_input)

    encoded_sequence = BatchNormalization()(encoded_sequence)

    encoded_sequence = Bidirectional(
        LSTM(32, activation="tanh", recurrent_activation='sigmoid', dropout=dropout, recurrent_dropout=dropout,
             return_sequences=True))(encoded_sequence)
    encoded_sequence = BatchNormalization()(encoded_sequence)

    encoded_sequence = Bidirectional(
        LSTM(32, activation="tanh", recurrent_activation='sigmoid', dropout=dropout, recurrent_dropout=dropout,
             return_sequences=False))(encoded_sequence)
    encoded_sequence = BatchNormalization()(encoded_sequence)

    # Currently predicting the next value based on seq_len windows
    out = Dense(window_size_y, activation='linear')(encoded_sequence)

    model = Model(seq_input, out)

    return model


seq_len = 3

Conv_LSTM_model = load_model("conv_lstm.hdf5")

# Data reshaping
X_train_Conv_MLP = X_train_windowed
y_train_Conv_MLP = window_output_train

X_test_Conv_MLP = X_test_windowed
y_test_Conv_MLP = window_output_test

X_test_Conv_LSTM = []
y_test_Conv_LSTM = []

for i in range(0, X_test_Conv_MLP.shape[0] - seq_len, window_size_x):
    current_seq_X = []
    current_seq_y = []
    for l in range(seq_len):
        current_seq_X.append(X_test_Conv_MLP[i + l])
        current_seq_y.append(y_test_Conv_MLP[i + l])
    X_test_Conv_LSTM.append(current_seq_X)
    y_test_Conv_LSTM.append(y_test_Conv_MLP[i+seq_len-1])

X_test_Conv_LSTM = np.array(X_test_Conv_LSTM)
X_test_Conv_LSTM = X_test_Conv_LSTM.reshape(-1, seq_len, img_size, img_size, 3)
y_test_Conv_LSTM = np.array(y_test_Conv_LSTM)
y_test_Conv_LSTM = y_test_Conv_LSTM.reshape(-1, window_size_y)

#=========================================================================================
# For if we want to generate on predicted
# y_preds = []
# X_test = X_test_Conv_LSTM[0,:,:,:,:]
# for i in tqdm(range(1000)):
#     X_test = X_test.reshape(1, seq_len, img_size, img_size, 3)
#     temp = Conv_LSTM_model.predict(X_test, verbose = 0, callbacks=None)
#     y = temp
#     y = y.reshape(1, -1)
#     y_preds.append(y)
#     last_two = X_test[0,1:,:,:,:]
#     gadf_transformed = np.expand_dims(gadf.fit_transform(y), axis=3)
#     gasf_transformed = np.expand_dims(gasf.fit_transform(y), axis=3)
#     mtf_transformed = np.expand_dims(mtf.fit_transform(y), axis=3)
#
#     prev_out = np.concatenate((gadf_transformed, gasf_transformed, mtf_transformed), axis=3)
#     X_test = np.concatenate((last_two,prev_out), axis=0)

# y_preds = np.asarray(y_preds)
# y_pred = y_preds.reshape(-1)

y_pred_Conv_LSTM = Conv_LSTM_model.predict(X_test_Conv_LSTM, verbose=1, callbacks=None)
y_pred = y_pred_Conv_LSTM[:,0]
print(y_pred.shape)
y_pred = y_pred.reshape(-1)

y_test = y_test_Conv_MLP[:,0]
y_test = y_test.reshape(-1)

show_result(y_test, y_pred, full=False)
