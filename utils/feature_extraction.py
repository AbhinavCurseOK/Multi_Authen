import logging
import librosa
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.layers import Layer
import pickle
import soundfile as sf

class L1Dist(Layer):
    def __init__(self, **kwargs):
        super().__init__()
    def call(self, input_base_model, validation_base_model):
        return tf.math.abs(input_base_model[0] - validation_base_model[0])

voice_verification_model = keras.models.load_model('models/best_model_verification_voice.keras')
fake_voice_model = keras.models.load_model('models/bestvoice_auth_model.keras')
face_verification_model = keras.models.load_model("models/th_best_siamesemodel.keras", custom_objects={'L1Dist': L1Dist})

with open('models/scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)


def extract_features(audio_path, label, sr=16000, segment_duration=2.0, overlap=0.5):
    try:
        audio, sr = librosa.load(audio_path, sr=sr)
    except Exception as e:
        logging.error(f"Error loading audio file: {audio_path}\nError: {e}")
        return []
    
    features = []
    segment_samples = int(segment_duration * sr)
    overlap_samples = int(overlap * sr)
    num_segments = max(1, (len(audio) - segment_samples) // (segment_samples - overlap_samples) + 1)

    for i in range(num_segments):
        start = i * (segment_samples - overlap_samples)
        end = start + segment_samples
        segment = audio[start:end]

        if len(segment) < segment_samples:
            segment = np.pad(segment, (0, segment_samples - len(segment)), mode='constant')

        n_fft = 512

        mfccs = librosa.feature.mfcc(y=segment, sr=sr, n_mfcc=13, n_fft=n_fft)
        delta_mfccs = librosa.feature.delta(mfccs)
        delta2_mfccs = librosa.feature.delta(mfccs, order=2)
        chroma = librosa.feature.chroma_stft(y=segment, sr=sr)
        spectral_centroid = librosa.feature.spectral_centroid(y=segment, sr=sr)
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=segment, sr=sr)
        rolloff = librosa.feature.spectral_rolloff(y=segment, sr=sr)
        zero_crossing_rate = librosa.feature.zero_crossing_rate(y=segment)
        S = np.abs(librosa.stft(segment))
        spectral_contrast = librosa.feature.spectral_contrast(S=S, sr=sr)

        if np.any(segment):
            tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(segment), sr=sr)
        else:
            tonnetz = np.zeros((6, segment_samples))

        feature_dict = {
            'mfcc': np.mean(mfccs, axis=1),
            'delta_mfccs': np.mean(delta_mfccs, axis=1),
            'delta2_mfccs': np.mean(delta2_mfccs, axis=1),
            'chroma': np.mean(chroma, axis=1),
            'spectral_centroid': np.mean(spectral_centroid),
            'spectral_bandwidth': np.mean(spectral_bandwidth),
            'rolloff': np.mean(rolloff),
            'zero_crossing_rate': np.mean(zero_crossing_rate),
            'spectral_contrast': np.mean(spectral_contrast, axis=1),
            'tonnetz': np.mean(tonnetz, axis=1),
        }
        features.append(feature_dict)
    if not features:
        logging.error(f"No features extracted from audio file: {audio_path}")
        return []

    return features

def verify_fake_voice(audio_path):
    features = extract_features(audio_path, label=None)
    if not features:
        logging.error(f"Failed to extract features from audio file: {audio_path}")
        return False

    features_df = pd.DataFrame([features[0]])
    X = pd.concat([
        pd.DataFrame(features_df['mfcc'].tolist()),
        pd.DataFrame(features_df['delta_mfccs'].tolist()),
        pd.DataFrame(features_df['delta2_mfccs'].tolist()),
        pd.DataFrame(features_df['chroma'].tolist()),
        features_df[['spectral_centroid', 'spectral_bandwidth', 'rolloff', 'zero_crossing_rate']],
        pd.DataFrame(features_df['spectral_contrast'].tolist()),
        pd.DataFrame(features_df['tonnetz'].tolist())
    ], axis=1)
    X.columns = X.columns.astype(str)
    X_scaled = scaler.transform(X)
    X_scaled = X_scaled.reshape(X_scaled.shape[0], X_scaled.shape[1], 1)
    prediction = fake_voice_model.predict(X_scaled)[0][0]
    print(prediction,"prediction")
    return prediction 


def load_audio(file_path, sr=22050, max_duration=5):
    try:
        y, _ = librosa.load(file_path, sr=sr)
    except Exception as e:
        logging.error(f"Error loading audio file: {file_path}\nError: {e}")
        return None

    target_length = sr * max_duration
    if len(y) > target_length:
        y = y[:target_length]
    else:
        y = np.pad(y, (0, target_length - len(y)))

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=64)
    return np.expand_dims(mfcc, axis=-1)
def preprocess(file_path):
    byte_img = tf.io.read_file(file_path)
    try:
        img = tf.io.decode_jpeg(byte_img, channels=3)
    except tf.errors.InvalidArgumentError:
        img = tf.io.decode_png(byte_img, channels=3)
    
    img = tf.image.resize(img, (100, 100))
    img = img / 255.0
    return img

def verify_myimage(image_path1, image_path2, threshold=0.5):
    try:
        img1 = preprocess(image_path1)
        img2 = preprocess(image_path2)
        img1 = tf.expand_dims(img1, axis=0)
        img2 = tf.expand_dims(img2, axis=0)
        prediction = face_verification_model.predict([img1, img2])
        logging.info(f"Prediction: {prediction[0][0]} ######")
        result = prediction[0][0] > threshold
        logging.info(f"Verification result: {result}")
        return result
    except Exception as e:
        logging.error(f"Error in verify_myimage: {e}")
        return False

def verify_myvoice(voice_path1, voice_path2, threshold=0.5):
    audio_saved = load_audio(voice_path1)
    audio_current = load_audio(voice_path2)

    if audio_saved is None or audio_current is None:
        logging.error("Failed to load one or both audio files for verification.")
        return False

    similarity_score = voice_verification_model.predict([
        np.expand_dims(audio_saved, axis=0),
        np.expand_dims(audio_current, axis=0)
    ])[0][0]
    print("score",similarity_score)
    return similarity_score > threshold
