import unittest
import logging
from utils.feature_extraction import verify_fake_voice, verify_myimage, verify_myvoice

class TestVerificationFunctions(unittest.TestCase):
    
    def test_verify_fake_voice(self):
        test_audio_path = "test_data/fake_voice.wav"
        prediction = verify_fake_voice(test_audio_path)
        logging.info(f"Fake voice prediction: {prediction}")
        self.assertIsInstance(prediction, bool)

    def test_verify_myimage(self):
        test_image_1 = "test_data/image1.jpg"
        test_image_2 = "test_data/image2.jpg"
        result = verify_myimage(test_image_1, test_image_2)
        logging.info(f"Face verification result: {result}")
        self.assertIsInstance(result, bool)

    def test_verify_myvoice(self):
        test_voice_1 = "test_data/voice1.wav"
        test_voice_2 = "test_data/voice2.wav"
        result = verify_myvoice(test_voice_1, test_voice_2)
        logging.info(f"Voice verification result: {result}")
        self.assertIsInstance(result, bool)

if __name__ == "__main__":
    unittest.main()
#need to update later#