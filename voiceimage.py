from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import firebase_admin
from flask_cors import CORS
from firebase_admin import credentials, storage, auth, db
import time
import tempfile
from datetime import datetime, timezone
import os
from utils.feature_extraction import verify_fake_voice, verify_myvoice, verify_myimage
import logging
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') 
CORS(app)

cred_dict = {
    "type": os.getenv("TYPE"),
    "project_id": os.getenv("PROJECT_ID"),
    "private_key_id": os.getenv("PRIVATE_KEY_ID"),
    "private_key": os.getenv("PRIVATE_KEY").replace('\\n', '\n'),
    "client_email": os.getenv("CLIENT_EMAIL"),
    "client_id": os.getenv("CLIENT_ID"),
    "auth_uri": os.getenv("AUTH_URI"),
    "token_uri": os.getenv("TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
    "universe_domain": os.getenv("UNIVERSE_DOMAIN")
}

cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(
    cred,
    {
        "databaseURL": os.getenv("DATABASE_URL"),
        "storageBucket": os.getenv("STORAGE_BUCKET"),
    },
)
bucket = storage.bucket()

@app.route('/firebase-config')
def firebase_config():
    config = {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID"),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID"),
        "measurementId": os.getenv("FIREBASE_MEASUREMENT_ID")
    }
    return jsonify(config)


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        username = request.form.get('username')
        if not email or not password or not username:
            return jsonify({'success': False, 'message': 'Username, email, and password are required.'})
        try:
            username_ref = db.reference('users').order_by_child('username').equal_to(username).get()
            if username_ref:
                return jsonify({'success': False, 'message': 'Username already taken. Choose another one.'})
            user = auth.create_user(email=email, password=password)
            user_id = user.uid
            registration_time = datetime.now(timezone.utc).isoformat()
            db.reference(f'users/{user_id}').set({
                'username': username,
                'email': email,
                'registration_time': registration_time,
                'last_login': None,
                'auth_mode': ['password'],
                'imageUrl': None,
                'voiceUrl': None
            })
            return jsonify({'success': True, 'message': 'Registration successful! Please select your authentication method.', 'user_id': user_id})
        except auth.EmailAlreadyExistsError:
            return jsonify({'success': False, 'message': 'Email already exists. Try logging in.'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    return render_template('register.html')

@app.route('/multi_auth', methods=['GET', 'POST'])
def multi_auth():
    user_id = request.args.get('user_id')
    if request.method == 'POST':
        auth_method = request.form.get('auth_method')
        if auth_method == 'image':
            return redirect(url_for('image_registration', user_id=user_id))
        elif auth_method == 'voice':
            return redirect(url_for('voice_registration', user_id=user_id))
        elif auth_method == 'both':
            return redirect(url_for('both_registration', user_id=user_id))
        else:
            flash('Invalid authentication method selected.', 'danger')
            return redirect(url_for('multi_auth', user_id=user_id))
    return render_template('multi_auth.html', user_id=user_id)

@app.route('/image_registration', methods=['POST'])
def image_registration():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'})
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image uploaded.'})
    image = request.files['image']
    filename = f"{user_id}_image_{int(time.time())}.png"    
    bucket = storage.bucket()
    blob = bucket.blob(f"uploads/{filename}")
    blob.upload_from_file(image)
    image_url = blob.public_url
    user_ref = db.reference(f'users/{user_id}')
    user_ref.update({'imageUrl': image_url})
    auth_mode = user_ref.child('auth_mode').get() or []
    if 'image' not in auth_mode:
        auth_mode.append('image')
    user_ref.update({'auth_mode': auth_mode})
    return jsonify({'success': True, 'message': 'Image saved successfully! Please log in.'})

@app.route('/voice_registration', methods=['POST'])
def voice_registration():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'})
    if 'audio' not in request.files:
        return jsonify({'success': False, 'message': 'No audio file uploaded.'})
    audio_file = request.files['audio']
    audio_path = 'temp_voice.wav'
    audio_file.save(audio_path)
    logging.info(f"Audio file saved to {audio_path}")
    if audio_file.mimetype != "audio/wav":
        return jsonify({'success': False, 'message': 'Invalid audio format! Must be WAV.'})
    try:
        bucket = storage.bucket()
        blob = bucket.blob(f"uploads/{user_id}_voice_{int(time.time())}.wav")
        blob.upload_from_filename(audio_path)
        voice_url = blob.public_url
        logging.info(f"Audio file uploaded to Firebase Storage: {voice_url}")
        downloaded_audio_path = download_file_from_storage(blob.name, 'wav')
        if not downloaded_audio_path:
            raise Exception("Failed to download the audio file from Firebase Storage.")
        prediction = verify_fake_voice(downloaded_audio_path)
        if prediction > 0.5:
            os.remove(downloaded_audio_path)
            delete_user_account(user_id)
            return jsonify({'success': False, 'message': 'Fake voice detected! Your account has been deleted. Please register again.'})
        user_ref = db.reference(f'users/{user_id}')
        user_ref.update({'voiceUrl': voice_url})
        auth_mode = user_ref.child('auth_mode').get() or []
        if 'voice' not in auth_mode:
            auth_mode.append('voice')
        user_ref.update({'auth_mode': auth_mode})
        os.remove(audio_path)
        os.remove(downloaded_audio_path)
        return jsonify({'success': True, 'message': 'Voice saved successfully!'})
    except Exception as e:
        logging.error(f"Error processing audio file: {e}")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return jsonify({'success': False, 'message': f'Voice registration failed: {e}'})

def download_file_from_storage(file_path, file_type):
    try:
        bucket = storage.bucket()
        blob = bucket.blob(file_path)  
        if not blob.exists():
            logging.error("File does not exist in Storage!")
            return None
        with tempfile.NamedTemporaryFile(suffix=f'.{file_type}', delete=False) as temp_file:
            temp_file_path = temp_file.name
            blob.download_to_filename(temp_file_path) 
            logging.info(f"File downloaded to: {temp_file_path}")
            return temp_file_path
    except Exception as e:
        logging.error(f"Error downloading file from Storage: {e}")
        return None

def delete_user_account(user_id):
    try:
        auth.delete_user(user_id)
        db.reference(f'users/{user_id}').delete()
        logging.info('Account deleted. Please re-register.')
        return redirect(url_for('register'))
    except Exception as e:
        logging.error(f"Error deleting account: {e}")
        return redirect(url_for('login'))

@app.route('/both_registration', methods=['POST'])
def both_registration():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'})
    try:
        bucket = storage.bucket()
        if 'audio' in request.files:
            audio = request.files['audio']
            audio_path = 'temp_audio.wav'
            audio.save(audio_path)
            voice_filename = f"uploads/{user_id}_voice_{int(time.time())}.wav"
            voice_blob = bucket.blob(voice_filename)
            voice_blob.upload_from_filename(audio_path)
            voice_url = voice_blob.public_url
            downloaded_audio_path = download_file_from_storage(voice_filename, 'wav')
            if not downloaded_audio_path:
                raise Exception("Failed to download the audio file from Firebase Storage.")
            prediction = verify_fake_voice(downloaded_audio_path)
            if prediction > 0.5:
                os.remove(downloaded_audio_path)
                delete_user_account(user_id)
                return jsonify({'success': False, 'message': 'Fake voice detected! Your account has been deleted. Please register again.'})
            os.remove(audio_path)
            os.remove(downloaded_audio_path)
            db.reference(f'users/{user_id}').update({'voiceUrl': voice_url})
            return jsonify({'success': True, 'message': 'Voice verification successful. Please capture your image.'})
        if 'image' in request.files:
            image = request.files['image']
            image_filename = f"uploads/{user_id}_image_{int(time.time())}.png"
            image_blob = bucket.blob(image_filename)
            image_blob.upload_from_file(image)
            image_url = image_blob.public_url
            user_ref = db.reference(f'users/{user_id}')
            user_ref.update({'imageUrl': image_url})
            auth_mode = user_ref.child('auth_mode').get() or []
            if 'voice' not in auth_mode:
                auth_mode.append('voice')
            if 'image' not in auth_mode:
                auth_mode.append('image')
            user_ref.update({'auth_mode': auth_mode})
            return jsonify({'success': True, 'message': 'Voice and image verification successful! Please log in.'})
        return jsonify({'success': False, 'message': 'No audio or image file uploaded.'})
    except ValueError as e:
        return jsonify({'success': False, 'message': f'Registration failed: {e}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'An unexpected error occurred: {e}'})

def increment_failed_attempts(user_id):
    ref = db.reference(f'users/{user_id}')
    user_data = ref.get()
    if not user_data:
        return
    failed_attempts = user_data.get('failed_attempts', 0) + 1
    if failed_attempts >= 5:
        flash('Too many failed attempts. Try password login or delete your account.', 'warning')
        session['failed_user'] = user_id
        session['failed_attempts'] = True  
    else:
        ref.update({'failed_attempts': failed_attempts})

@app.route('/handle_failed_login', methods=['POST'])
def handle_failed_login():
    user_id = session.get('failed_user')
    if not user_id:
        return redirect(url_for('login'))
    action = request.form.get('action')
    if action == 'delete':
        session.pop('failed_user', None)
        return delete_user_account(user_id)
    elif action == 'password':
        flash('Please log in using your password.', 'info')
        session.pop('failed_user', None)
        return redirect(url_for('login'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email is required!', 'danger')
            return redirect(url_for('login'))
        try:
            users_ref = db.reference('users')
            all_users = users_ref.get()
            user_data = None
            user_id = None
            for uid, data in all_users.items():
                if data.get('email') == email:
                    user_data = data
                    user_id = uid
                    break
            if not user_data:
                flash('Email not found. Please register.', 'danger')
                return redirect(url_for('register'))
            session['pending_uid'] = user_id
            session['auth_methods'] = user_data.get('auth_mode', [])
            return redirect(url_for('verify_options', user_id=user_id))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/verify_options', methods=['GET'])
def verify_options():
    user_id = request.args.get('user_id')
    user_ref = db.reference(f'users/{user_id}')
    user_data = user_ref.get()
    auth_methods = user_data.get('auth_mode', [])
    return render_template('verify_options.html', auth_methods=auth_methods, user_id=user_id)

@app.route('/verify_image', methods=['POST'])
def verify_image():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'}), 400
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image uploaded.'}), 400
    image_file = request.files['image']
    try:
        bucket = storage.bucket()
        verify_image_filename = f"verify_user/{user_id}_verify_image_{int(time.time())}.png"
        verify_image_blob = bucket.blob(verify_image_filename)
        verify_image_blob.upload_from_file(image_file)
        verify_image_url = verify_image_blob.public_url
        logging.info(f"Verification image uploaded to Firebase Storage: {verify_image_url}")
        downloaded_verify_image_path = download_file_from_storage(verify_image_filename, 'png')
        if not downloaded_verify_image_path:
            raise Exception("Failed to download the verification image from Firebase Storage.")
        user_ref = db.reference(f'users/{user_id}')
        image_url = user_ref.child('imageUrl').get()
        if not image_url:
            raise Exception("No image URL found for the user.")
        logging.info(f"Image URL: {image_url}")
        relative_image_path = '/'.join(image_url.split('/')[4:])          
        image_path_of = download_file_from_storage(relative_image_path, 'png')
        if not image_path_of:
            raise Exception("Failed to download the original image from Firebase Storage.")
        if not verify_myimage(downloaded_verify_image_path, image_path_of, threshold=0.5):
            increment_failed_attempts(user_id)
            return jsonify({'success': False, 'message': 'Image verification failed! Please try again.'}), 400
        #user_ref.child('failed_attempts').delete()
        #logging.info(f"Failed attempts deleted for user: {user_id}")
        logging.info(f"Image verification successful for user: {user_id}")
        return jsonify({'success': True, 'message': 'Image verification successful! Welcome!'}), 200
    except Exception as e:
        logging.error(f"Error processing image file: {e}")
        return jsonify({'success': False, 'message': f'Image verification failed: {e}'}), 500
    finally:
        try:
            verify_image_blob.delete()
            logging.info(f"Verification image deleted from Firebase Storage: {verify_image_filename}")
        except Exception as e:
            logging.error(f"Error deleting verification image from Firebase Storage: {e}")
        if os.path.exists(downloaded_verify_image_path):
            os.remove(downloaded_verify_image_path)
        if os.path.exists(image_path_of):
            os.remove(image_path_of)

@app.route('/verify_voice', methods=['POST'])
def verify_voice():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'}), 400
    if 'audio' not in request.files:
        return jsonify({'success': False, 'message': 'No audio file uploaded.'}), 400
    audio_file = request.files['audio']
    audio_path = 'temp_voice.wav'
    voice_path_of = None
    downloaded_verify_voice_path = None
    try:
        audio_file.save(audio_path)
        logging.info(f"Audio file saved to {audio_path}")
        bucket = storage.bucket()
        verify_voice_filename = f"verify_user/{user_id}_verify_voice_{int(time.time())}.wav"
        verify_voice_blob = bucket.blob(verify_voice_filename)
        verify_voice_blob.upload_from_filename(audio_path)
        verify_voice_url = verify_voice_blob.public_url
        logging.info(f"Verification audio uploaded to Firebase Storage: {verify_voice_url}")
        user_ref = db.reference(f'users/{user_id}')
        voice_url = user_ref.child('voiceUrl').get()
        if not voice_url:
            raise Exception("No voice URL found for the user.")
        logging.info(f"Voice URL: {voice_url}")
        relative_voice_path = '/'.join(voice_url.split('/')[4:]) 
        voice_path_of = download_file_from_storage(relative_voice_path, 'wav')
        if not voice_path_of:
            raise Exception("Failed to download the original voice from Firebase Storage.")
        downloaded_verify_voice_path = download_file_from_storage(verify_voice_filename, 'wav')
        if not downloaded_verify_voice_path:
            raise Exception("Failed to download the verification voice from Firebase Storage.")
        prediction = verify_fake_voice(downloaded_verify_voice_path)
        if prediction > 0.5:
            increment_failed_attempts(user_id)
            #failed_attempts = user_ref.child('failed_attempts').get()
            return jsonify({'success': False, 'message': f'Fake voice detected! Failed attempts'}), 400
        if not verify_myvoice(downloaded_verify_voice_path, voice_path_of, threshold=0.5):
            increment_failed_attempts(user_id)
            #failed_attempts = user_ref.child('failed_attempts').get()
            return jsonify({'success': False, 'message': f'Voice verification failed! Failed attempts'}), 400
        #user_ref.update({'failed_attempts': 0})
        os.remove(audio_path)
        os.remove(downloaded_verify_voice_path)
        os.remove(voice_path_of)
        return jsonify({'success': True, 'message': 'Voice verification successful! Welcome!'}), 200
    except Exception as e:
        logging.error(f"Error processing audio file: {e}")
        return jsonify({'success': False, 'message': f'Voice verification failed: {e}'}), 500
    finally:
        try:
            verify_voice_blob.delete()
            logging.info(f"Verification audio deleted from Firebase Storage: {verify_voice_filename}")
        except Exception as e:
            logging.error(f"Error deleting verification audio from Firebase Storage: {e}")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if downloaded_verify_voice_path and os.path.exists(downloaded_verify_voice_path):
            os.remove(downloaded_verify_voice_path)
        if voice_path_of and os.path.exists(voice_path_of):
            os.remove(voice_path_of)

@app.route('/verify_both', methods=['POST'])
def verify_both():
    user_id = request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'User ID is required.'}), 400
    if 'audio' not in request.files or 'image' not in request.files:
        return jsonify({'success': False, 'message': 'Both audio and image files are required.'}), 400
    audio_file = request.files['audio']
    image_file = request.files['image']
    audio_path = 'temp_voice.wav'
    image_path = 'temp_image.png'
    downloaded_audio_path = None
    downloaded_image_path = None
    original_voice_path = None
    original_image_path = None
    try:
        audio_file.save(audio_path)
        image_file.save(image_path)
        logging.info(f"Audio file saved to {audio_path}")
        logging.info(f"Image file saved to {image_path}")
        bucket = storage.bucket()
        verify_audio_filename = f"verify_user/{user_id}_verify_voice_{int(time.time())}.wav"
        verify_image_filename = f"verify_user/{user_id}_verify_image_{int(time.time())}.png"
        verify_audio_blob = bucket.blob(verify_audio_filename)
        verify_image_blob = bucket.blob(verify_image_filename)
        verify_audio_blob.upload_from_filename(audio_path)
        verify_image_blob.upload_from_filename(image_path)
        logging.info(f"Verification audio uploaded: {verify_audio_filename}")
        logging.info(f"Verification image uploaded: {verify_image_filename}")
        downloaded_audio_path = download_file_from_storage(verify_audio_filename, 'wav')
        downloaded_image_path = download_file_from_storage(verify_image_filename, 'png')
        if not downloaded_audio_path or not downloaded_image_path:
            raise Exception("Failed to download verification files from Firebase Storage.")
        user_ref = db.reference(f'users/{user_id}')
        voice_url = user_ref.child('voiceUrl').get()
        if not voice_url:
            raise Exception("No voice URL found for the user.")
        relative_voice_path = '/'.join(voice_url.split('/')[4:])  
        original_voice_path = download_file_from_storage(relative_voice_path, 'wav')
        if not original_voice_path:
            raise Exception("Failed to download the original voice from Firebase Storage.")
        prediction = verify_fake_voice(downloaded_audio_path)
        if prediction > 0.5:
            increment_failed_attempts(user_id)
            return jsonify({'success': False, 'message': 'Fake voice detected!'}), 400
        if not verify_myvoice(downloaded_audio_path, original_voice_path, threshold=0.5):
            increment_failed_attempts(user_id)
            return jsonify({'success': False, 'message': 'Voice verification failed!'}), 400
        image_url = user_ref.child('imageUrl').get()
        if not image_url:
            raise Exception("No image URL found for the user.")
        relative_image_path = '/'.join(image_url.split('/')[4:])  
        original_image_path = download_file_from_storage(relative_image_path, 'png')
        if not original_image_path:
            raise Exception("Failed to download the original image from Firebase Storage.")
        if not verify_myimage(downloaded_image_path, original_image_path, threshold=0.5):
            increment_failed_attempts(user_id)
            return jsonify({'success': False, 'message': 'Image verification failed!'}), 400
        #user_ref.update({'failed_attempts': 0})
        os.remove(audio_path)
        os.remove(image_path)
        os.remove(downloaded_audio_path)
        os.remove(downloaded_image_path)
        os.remove(original_voice_path)
        os.remove(original_image_path)
        return jsonify({'success': True, 'message': 'Both verification successful! Welcome!'}), 200
    except Exception as e:
        logging.error(f"Error processing files: {e}")
        return jsonify({'success': False, 'message': f'Both verification failed: {e}'}), 500
    finally:
        try:
            verify_audio_blob.delete()
            verify_image_blob.delete()
            logging.info("Verification files deleted from Firebase Storage.")
        except Exception as e:
            logging.error(f"Error deleting verification files from Firebase Storage: {e}")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(image_path):
            os.remove(image_path)
        if downloaded_audio_path and os.path.exists(downloaded_audio_path):
            os.remove(downloaded_audio_path)
        if downloaded_image_path and os.path.exists(downloaded_image_path):
            os.remove(downloaded_image_path)
        if original_voice_path and os.path.exists(original_voice_path):
            os.remove(original_voice_path)
        if original_image_path and os.path.exists(original_image_path):
            os.remove(original_image_path)

@app.route('/protected', methods=['GET'])
def protected():
    try:
        id_token = request.headers.get("Authorization")
        if not id_token:
            return jsonify({"error": "No ID token provided"}), 401
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token["uid"]
        return jsonify({"message": "Access granted", "uid": user_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route('/verify_passwordnew')
def verify_passwordnew():
    user_id = request.args.get('user_id')
    return render_template('verify_password.html', user_id=user_id)

@app.route('/verify_imagenew')
def verify_imagenew():
    user_id = request.args.get('user_id')
    return render_template('verify_image.html', user_id=user_id)

@app.route('/verify_voicenew')
def verify_voicenew():
    user_id = request.args.get('user_id')
    return render_template('verify_voice.html', user_id=user_id)

@app.route('/verify_bothnew')
def verify_bothnew():
    user_id = request.args.get('user_id')
    return render_template('verify_both.html', user_id=user_id)

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)




#