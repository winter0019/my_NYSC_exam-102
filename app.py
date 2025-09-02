import os
import uuid
import json
import re
import logging
import hashlib
from io import BytesIO
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_from_directory, flash
from flask_cors import CORS
from docx import Document
# Removed load_dotenv() as it's not needed on Render
import google.generativeai as genai
from google.api_core import exceptions
import PyPDF2
import requests
import pytesseract
from PIL import Image
import fitz # PyMuPDF for better PDF text extraction


# Try to import optional dependencies
try:
    import firebase_admin
    from firebase_admin import credentials, firestore, auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("Firebase Admin SDK not available. Some features will be disabled.")

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    print("Flask-Limiter not available. Rate limiting will be disabled.")

# --- Whitelisted Users ---
ALLOWED_USERS = {
    "deborahibiyinka@gmail.com",
    "feuri73@gmail.com",
    "zainabsalawu1989@gmail.com",
    "alograce69@gmail.com", 
    "abdullahimuhd790@gmail.com",
    "davidirene2@gmail.com",
    "maryaugie2@gmail.com",
    "ashami73@gmail.com",
    "comzelhua@gmail.com",
    "niyiolaniyi@gmail.com",
    "itszibnisah@gmail.com",
    "olayemisiola06@gmail.com",
    "shemasalik@gmail.com",
    "akawupeter2@gmail.com",
    "pantuyd@gmail.com",
    "omnibuszara@gmail.com",
    "mssphartyma@gmail.com",
    "assyy.au@gmail.com",
    "shenyshehu@gmail.com",
    "isadeeq17@gmail.com",
    "muhammadsadanu@gmail.com",
    "rukitafida@gmail.com",
    "dangalan20@gmail.com",
    "winter19@gmail.com",
    "adedoyinfehintola@gmail.com",
}

# Normalize emails to lowercase
ALLOWED_USERS = {email.lower() for email in ALLOWED_USERS}

# --- Track active sessions ---
active_sessions = {}  # {email: session_id}
user_sessions = {}

# --- Setup ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)

# Rate limiting (if available)
if LIMITER_AVAILABLE:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
else:
    def limiter_limit(limit_str):
        def decorator(f):
            return f
        return decorator
    limiter = type('DummyLimiter', (), {'limit': lambda self, limit_str: limiter_limit(limit_str)})()

# In-memory storage with expiration for rooms
rooms = {}

# --- Firebase Setup ---
db = None
if FIREBASE_AVAILABLE:
    try:
        # This is the corrected way to handle credentials from environment variables
        if os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
            cred_json = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))
            cred = credentials.Certificate(cred_json)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            logger.info("Firebase initialized successfully")
        else:
            logger.warning("Firebase credentials environment variable not found. Firebase features disabled.")
    except Exception as e:
        logger.warning(f"Firebase init failed: {e}")
        db = None
else:
    logger.warning("Firebase not available. Some features will be disabled.")

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")

# --- Authentication Decorator (assuming this exists in your code) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            flash("Please log in to access this page.")
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def fetch_user_history(email, limit=10):
    if not db:
        return []
    
    # Assuming the user ID is stored in the session
    user_id = session.get("user_id")
    if not user_id:
        return []

    try:
        history_ref = db.collection('users').document(user_id).collection('history')
        docs = history_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        history = [doc.to_dict() for doc in docs]
        return history
    except Exception as e:
        logger.error(f"Error fetching user history for {email}: {e}")
        return []

def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def validate_grade(grade):
    return grade in ["GL10", "GL11", "GL12"]

# --- Routes ---
@app.route("/", methods=["GET"])
def login_page():
    if "user_email" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Email and password are required")
            return redirect(url_for("login"))

        try:
            # Firebase REST API authentication
            auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
            auth_data = {
                "email": email,
                "password": password,
                "returnSecureToken": True
            }
            
            response = requests.post(auth_url, json=auth_data)
            response.raise_for_status()
            user_data = response.json()
            
            # Generate session ID and store user info
            session["user_email"] = email
            session["user_id"] = user_data.get("localId", "")
            
            logger.info(f"User logged in: {email}")
            return redirect(url_for("dashboard"))
            
        except requests.exceptions.HTTPError as e:
            error_msg = "Invalid email or password"
            if "EMAIL_NOT_FOUND" in str(e) or "INVALID_PASSWORD" in str(e):
                error_msg = "Invalid email or password"
            elif "USER_DISABLED" in str(e):
                error_msg = "Account disabled"
            flash(error_msg)
            return redirect(url_for("login"))
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash("Login failed. Please try again.")
            return redirect(url_for("login"))

@app.route("/signup", methods=["POST"])
@limiter.limit("3 per minute")
def signup():
    if request.is_json:
        data = request.get_json(force=True)
    else:
        data = request.form
    
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    grade = (data.get("grade") or "GL10").strip()
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    if email not in ALLOWED_USERS:
        logger.warning(f"Signup attempt from non-whitelisted email: {email}")
        return jsonify({"error": "Signup restricted. Contact admin."}), 403
    
    if not validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400
    
    if not validate_grade(grade):
        return jsonify({"error": "Invalid grade level"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    try:
        r = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10
        )
        r.raise_for_status()
        user_data = r.json()
        
        session["user_email"] = email
        session["user_grade"] = grade
        session["user_id"] = user_data.get("localId", "")
        
        if db:
            user_profile = {
                'email': email,
                'grade': grade,
                'created_at': datetime.now(),
                'last_login': datetime.now()
            }
            db.collection('users').document(user_data.get("localId")).set(user_profile)
        
        logger.info(f"New user registered: {email}")
        return jsonify({"ok": True, "email": user_data["email"], "idToken": user_data["idToken"]})
    
    except requests.exceptions.HTTPError as e:
        error_msg = "Could not create user"
        if "EMAIL_EXISTS" in str(e):
            error_msg = "Email already exists"
        logger.warning(f"Failed signup attempt for {email}: {e}")
        return jsonify({"error": error_msg}), 400
    except Exception as e:
        logger.error(f"Unexpected error during signup: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login_page"))

@app.route('/dashboard')
@login_required
def dashboard():
    email = session.get("user_email")
    if not email:
        return redirect(url_for('login_page'))

    admin_email = "dangalan20@gmail.com"
    is_admin = email == admin_email

    if is_admin:
        # Admin sees overview of all users
        users_data = {}
        try:
            if db:
                users_ref = db.collection("users").stream()
                for user_doc in users_ref:
                    user_data = user_doc.to_dict()
                    user_email = user_data.get('email', 'Unknown')
                    history_ref = user_doc.reference.collection("history")
                    history = [doc.to_dict() for doc in history_ref.stream()]
                    
                    # Convert timestamps if necessary
                    for item in history:
                        if 'timestamp' in item and hasattr(item['timestamp'], 'isoformat'):
                            item['timestamp'] = item['timestamp'].isoformat()
                            
                    users_data[user_email] = history
        except Exception as e:
            logger.error(f"Error fetching users overview: {e}")
            users_data = {}
        return render_template("admin_dashboard.html", users_data=users_data, email=email)
    else:
        # Normal user sees personal dashboard
        history = []
        try:
            history = fetch_user_history(email, limit=10)
            formatted_history = []
            for item in history:
                if 'timestamp' in item and hasattr(item['timestamp'], 'isoformat'):
                    item['timestamp'] = item['timestamp'].isoformat()
                formatted_history.append(item)
            history = formatted_history
        except Exception as e:
            logger.error(f"Error fetching history for {email}: {e}")
            
        grade = session.get("user_grade", "GL10")

        return render_template("dashboard.html", 
                               user_email=email, 
                               history=history,
                               grade=grade)

# --- Free Trial Quiz Route ---
@app.route("/free_trial_quiz")
@login_required
def free_trial_quiz():
    """Render free trial quiz page"""
    return render_template("free_trial_quiz.html", email=session["user_email"])

# --- Generate Free Trial Quiz ---
@app.route("/generate_free_quiz", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def generate_free_quiz():
    """Generate free trial quiz without document upload"""
    try:
        data = request.get_json()
        gl = (data.get("gl") or session.get("user_grade", "GL10")).strip()
        subject = (data.get("subject") or "public-service-rules").strip()

        subject_map = {
            "public-service-rules": "Public Service Rules",
            "nysc": "NYSC Operations and History",
            "current-affairs": "Current Nigerian & Global Affairs",
            "general-knowledge": "General Knowledge"
        }
        subject_prompt = subject_map.get(subject, "General Knowledge")

        # Use preset quiz generation for free trial
        cache_key = generate_cache_key(f"free_{gl}_{subject}", 5, "preset")
        
        cached_quiz = get_cached_quiz(cache_key)
        if cached_quiz:
            created_discussions = create_discussion_rooms(cached_quiz.get("discussions", []))
            cached_quiz["discussions"] = created_discussions
            log_quiz_activity(session["user_email"], "free_trial", subject)
            return jsonify(cached_quiz)

        prompt_text = f"""
You are an expert Nigerian promotional exam setter. 
Always respond in valid JSON.
Schema:
{{
  "quiz": [
    {{"question": "...", "options": ["A","B","C","D"], "correct": "A"}},
    ...
  ],
  "discussions": [
    {{"q": "..."}},
    ...
  ]
}}

Grade Level: {gl}
Subject: {subject_prompt}

Generate exactly:
- 5 multiple choice questions (MCQs) about {subject_prompt}
- 2 discussion questions related to {subject_prompt}
"""
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        raw = response.text.strip() if response and hasattr(response, "text") else "{}"
        data = json_hard_extract(raw)
        data = coerce_schema(data)

        data["discussions"] = create_discussion_rooms(data.get("discussions", []))
        store_quiz_in_cache(cache_key, data)
        log_quiz_activity(session["user_email"], "free_trial", subject)
        
        return jsonify(data)
    except exceptions.ResourceExhausted as e:
        logger.error(f"Gemini API quota exceeded: {e}", exc_info=True)
        return jsonify({
            "error": "Daily quiz generation limit reached. Please try again tomorrow."
        }), 429
    except Exception as e:
        logger.error(f"ERROR in /generate_free_quiz: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate quiz. Please try again."}), 500
        
# --- Document Upload Quiz ---
@app.route("/generate", methods=["POST"])
@login_required
@limiter.limit("5 per hour")
def generate_from_document():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No main file provided"}), 400

        main_file = request.files['file']
        if main_file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if not validate_file_extension(main_file.filename, ['docx', 'pdf', 'png', 'jpg', 'jpeg']):
            return jsonify({"error": "Invalid file type. Only DOCX, PDF, PNG, JPG allowed."}), 400

        past_file = request.files.get('past_file')
        if past_file and past_file.filename != '':
            if not validate_file_extension(past_file.filename, ['docx', 'pdf', 'png', 'jpg', 'jpeg']):
                return jsonify({"error": "Invalid past file type. Only DOCX, PDF, PNG, JPG allowed."}), 400

        grade = request.form.get("gl") or session.get("user_grade", "GL10")
        subject = request.form.get("subject") or "General Knowledge"
        force_new = request.form.get("force_new", "false").lower() == "true"

        text_main, text_past = "", ""
        if main_file:
            if main_file.filename.endswith(".docx"):
                text_main = extract_text_from_docx(main_file)
            elif main_file.filename.endswith(".pdf"):
                text_main = extract_text_from_pdf(main_file)
                if not text_main:  # fallback
                    text_main = extract_text_from_pdf_fitz(main_file)
            else:  # images
                text_main = extract_text_from_image(main_file)

        if past_file and past_file.filename:
            if past_file.filename.endswith(".docx"):
                text_past = extract_text_from_docx(past_file)
            elif past_file.filename.endswith(".pdf"):
                text_past = extract_text_from_pdf(past_file)
                if not text_past:
                    text_past = extract_text_from_pdf_fitz(past_file)
            else:  # images
                text_past = extract_text_from_image(past_file)

        if not text_main and not text_past:
            return jsonify({"error": "Could not extract text from the provided files"}), 400

        cache_key = generate_cache_key(
            f"{hashlib.md5(text_main.encode()).hexdigest()}_{hashlib.md5(text_past.encode()).hexdigest()}",
            5,
            "document"
        )

        if not force_new:
            cached_quiz = get_cached_quiz(cache_key)
            if cached_quiz:
                created_discussions = create_discussion_rooms(cached_quiz.get("discussions", []))
                cached_quiz["discussions"] = created_discussions
                log_quiz_activity(session["user_email"], "document", subject)
                return jsonify(cached_quiz)

        combined_text = f"""
Grade Level: {grade}
Subject: {subject}

Main Document:
{text_main[:4000]}

Past Questions:
{text_past[:4000]}
"""

        prompt_text = f"""
You are an expert Nigerian exam question generator. 
Always respond in valid JSON.
Schema:
{{
  "quiz": [
    {{"question": "...", "options": ["A","B","C","D"], "correct": "A"}},
    ...
  ],
  "discussions": [
    {{"q": "..."}},
    ...
  ]
}}

Source Material:
{combined_text}

Generate:
- 5 multiple choice questions (MCQs)
- 2 discussion questions
"""

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt_text, generation_config={"response_mime_type": "application/json"})
        raw = response.text.strip() if response and hasattr(response, "text") else "{}"
        data = json_hard_extract(raw)
        data = coerce_schema(data)

        data["discussions"] = create_discussion_rooms(data.get("discussions", []))
        store_quiz_in_cache(cache_key, data)
        log_quiz_activity(session["user_email"], "document", subject)

        return jsonify(data)

    except exceptions.ResourceExhausted as e:
        logger.error(f"Gemini API quota exceeded: {e}", exc_info=True)
        return jsonify({"error": "Daily quiz generation limit reached. Please try again tomorrow."}), 429
    except Exception as e:
        logger.error(f"ERROR in /generate: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate quiz. Please try again."}), 500

# --- Discussion Room Routes ---
@app.route('/discussion/<room_id>')
@login_required
def discussion_room(room_id):
    try:
        # Try to get room from Firestore first, then fallback to memory
        room = None
        if db:
            room_doc = db.collection('discussion_rooms').document(room_id).get()
            if room_doc.exists:
                room = room_doc.to_dict()
        
        # Fallback to in-memory storage
        if not room:
            room = rooms.get(room_id)
        
        if not room:
            return "Discussion room not found", 404
        
        return render_template('discussion.html', room_id=room_id, question=room['question'])
    
    except Exception as e:
        logger.error(f"Error accessing discussion room {room_id}: {e}")
        return "An error occurred while accessing the discussion room", 500

@app.route('/check_auth')
@login_required
def check_auth():
    """Simple endpoint to check if user is authenticated"""
    try:
        # Check if user session is valid
        if "user_email" not in session:
            return jsonify({"authenticated": False, "error": "No active session"}), 401
        
        email = session["user_email"]
        session_id = session.get("session_id")
        
        # Verify session is still active
        if active_sessions.get(email) != session_id:
            session.clear()
            return jsonify({"authenticated": False, "error": "Session expired"}), 401
        
        # Return success with user info
        return jsonify({
            "authenticated": True, 
            "email": email,
            "grade": session.get("user_grade", "GL10"),
            "user_id": session.get("user_id", "")
        })
    
    except Exception as e:
        logger.error(f"Error in check_auth: {e}")
        return jsonify({"authenticated": False, "error": "Internal server error"}), 500

@app.route('/messages/<room_id>')
@login_required
@limiter.limit("200 per hour")  # Increased from 50 to 200 per hour
def get_messages(room_id):
    # ... your existing code ...
    try:
        messages = []
        
        # Try to get messages from Firestore first
        if db:
            room_ref = db.collection('discussion_rooms').document(room_id)
            room_doc = room_ref.get()
            if room_doc.exists:
                room_data = room_doc.to_dict()
                messages = room_data.get('messages', [])
        
        # Fallback to in-memory storage
        if not messages:
            room = rooms.get(room_id)
            if room:
                messages = room.get('messages', [])
            else:
                return jsonify({"error": "Room not found"}), 404
        
        # Get unique participants
        participants = set(msg.get('user', 'Anonymous') for msg in messages)
        
        # Get final answer if exists
        final_answer = None
        if db:
            room_doc = db.collection('discussion_rooms').document(room_id).get()
            if room_doc.exists:
                final_answer = room_doc.to_dict().get('final_answer')
        
        return jsonify({
            "messages": messages,
            "final_answer": final_answer,
            "participants": len(participants)
        })
    
    except Exception as e:
        logger.error(f"Error fetching messages for room {room_id}: {e}")
        return jsonify({"error": "Failed to fetch messages"}), 500

@app.route('/message/<room_id>', methods=['POST'])
@login_required
def post_message(room_id):
    try:
        data = request.get_json()
        user = data.get('user', session.get("user_email", "Anonymous"))
        text = data.get('text', '').strip()
        
        if not text:
            return jsonify({"error": "Message text is required"}), 400
        
        message = {
            "user": user,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "user_email": session.get("user_email", "")  # Store actual user email for tracking
        }
        
        # Try to save to Firestore first
        if db:
            try:
                room_ref = db.collection('discussion_rooms').document(room_id)
                
                # Update the room with new message and timestamp
                room_ref.update({
                    'messages': firestore.ArrayUnion([message]),
                    'last_activity': firestore.SERVER_TIMESTAMP,
                    'participants': firestore.ArrayUnion([session.get("user_email", "Anonymous")])
                })
            except Exception as firestore_error:
                logger.warning(f"Firestore update failed, using in-memory: {firestore_error}")
                # Fallback to in-memory if Firestore fails
                room = rooms.get(room_id)
                if not room:
                    return jsonify({"error": "Room not found"}), 404
                room['messages'].append(message)
                room['last_activity'] = datetime.now()
        else:
            # Use in-memory storage only
            room = rooms.get(room_id)
            if not room:
                return jsonify({"error": "Room not found"}), 404
            room['messages'].append(message)
            room['last_activity'] = datetime.now()
        
        # Log the message activity
        log_quiz_activity(session["user_email"], "discussion", f"Room: {room_id}")
        
        return jsonify({"ok": True, "message": message})
    
    except Exception as e:
        logger.error(f"Error posting message to room {room_id}: {e}")
        return jsonify({"error": "Failed to post message"}), 500

@app.route('/summarize/<room_id>', methods=['POST'])
@login_required
@limiter.limit("3 per hour")
def summarize_room(room_id):
    try:
        # Get messages from Firestore or memory
        messages = []
        if db:
            room_doc = db.collection('discussion_rooms').document(room_id).get()
            if room_doc.exists:
                messages = room_doc.to_dict().get('messages', [])
        
        if not messages:
            room = rooms.get(room_id)
            if room:
                messages = room.get('messages', [])
            else:
                return jsonify({"error": "Room not found"}), 404
        
        # Check if there are enough messages to summarize
        if len(messages) < 3:
            return jsonify({"error": "Not enough messages to summarize"}), 400
        
        try:
            # Build a prompt from the discussion messages
            discussion_text = "\n".join([f"{m.get('user', 'Anonymous')}: {m.get('text', '')}" for m in messages])
            prompt = f"""
            Summarize the key points from this discussion about '{room['question']}'.
            Provide a comprehensive answer that captures the collective wisdom of the participants.
            
            Discussion:
            {discussion_text}
            
            Provide your summary in a clear, structured format.
            """
            
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            summary = response.text
            
            # Save summary to Firestore or memory
            if db:
                db.collection('discussion_rooms').document(room_id).update({
                    'final_answer': summary,
                    'last_activity': firestore.SERVER_TIMESTAMP
                })
            else:
                room = rooms.get(room_id)
                if room:
                    room['final_answer'] = summary
                    room['last_activity'] = datetime.now()
            
            # Log the summarization activity
            log_quiz_activity(session["user_email"], "summary", f"Room: {room_id}")
            
            return jsonify({"summary": summary})
        
        except exceptions.ResourceExhausted as e:
            logger.error(f"Gemini API quota exceeded: {e}")
            return jsonify({
                "error": "Summary generation limit reached. Please try again later."
            }), 429
        
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return jsonify({"error": "Failed to generate summary"}), 500
    
    except Exception as e:
        logger.error(f"Error in summarize endpoint for room {room_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500
    
# --- Per-user quizzes storage (in-memory fallback) ---
user_quizzes = {}  # { email: [ {id, subject, quiz, created_at, source} ] }

def save_user_quiz(user_email, quiz_data, subject="unspecified", source="preset"):
    """
    Store generated quiz data under the user's history.
    Uses Firestore if available, otherwise stores in-memory.
    Returns stored record (including id and timestamp).
    """
    record = {
        "id": str(uuid.uuid4()),
        "subject": subject,
        "quiz": quiz_data.get("quiz", []),
        "discussions": quiz_data.get("discussions", []),
        "source": source,
        "created_at": datetime.now()
    }

    # Save to Firestore if available
    try:
        if db:
            db.collection("user_quizzes").document(record["id"]).set({
                **record,
                "user_email": user_email,
                "created_at": firestore.SERVER_TIMESTAMP
            })
        else:
            # In-memory fallback
            user_quizzes.setdefault(user_email, []).insert(0, record)
    except Exception as e:
        logger.warning(f"Failed to save user quiz: {e}")
        # Always keep fallback
        user_quizzes.setdefault(user_email, []).insert(0, record)

    return record

def fetch_user_history(user_email, limit=10):
    """Return latest quiz records for the given user."""
    results = []
    if db:
        try:
            docs = db.collection('user_quizzes').where('user_email', '==', user_email).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).stream()
            for d in docs:
                data = d.to_dict()
                # normalize timestamp for display
                ts = data.get("created_at")
                data["created_at"] = ts if not hasattr(ts, "isoformat") else ts.isoformat()
                results.append(data)
            return results
        except Exception as e:
            logger.warning(f"Failed fetch_user_history from Firestore: {e}")
    # fallback to in-memory store
    for r in user_quizzes.get(user_email, [])[:limit]:
        copy = dict(r)
        copy["created_at"] = copy["created_at"].isoformat() if isinstance(copy["created_at"], datetime) else copy["created_at"]
        results.append(copy)
    return results

# --- Create public discussion room (UI + endpoint used by dashboard) ---
@app.route("/create_room", methods=["GET", "POST"])
@login_required
def create_room():
    if request.method == "GET":
        return render_template("create_room.html")
    
    # POST -> create room
    q = (request.form.get("question") or request.json and request.json.get("question") or "").strip()
    if not q:
        return jsonify({"error": "Question text is required"}), 400

    room_id = str(uuid.uuid4())
    room_doc = {
        "question": q,
        "messages": [],
        "final_answer": None,
        "created_by": session.get("user_email"),
        "created_at": datetime.now(),
        "last_activity": datetime.now(),
        "public": True
    }
    rooms[room_id] = room_doc

    # Persist to Firestore if possible
    if db:
        try:
            db.collection("discussion_rooms").document(room_id).set({
                **room_doc,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_activity": firestore.SERVER_TIMESTAMP,
            })
        except Exception as e:
            logger.warning(f"Failed to persist discussion room: {e}")

    return redirect(url_for("discussion_room", room_id=room_id))

# --- public discussion listing (so dashboard can link to '/discussion') ---
@app.route("/discussion", methods=["GET"])
@login_required
def discussion_index():
    """
    Show list of public discussion rooms. Dashboard will link here.
    """
    public_rooms = []
    # prefer Firestore if available
    if db:
        try:
            docs = db.collection("discussion_rooms").where("public", "==", True).order_by("last_activity", direction=firestore.Query.DESCENDING).stream()
            for d in docs:
                r = d.to_dict()
                r["id"] = d.id
                public_rooms.append(r)
        except Exception as e:
            logger.warning(f"Failed to fetch public rooms from Firestore: {e}")

    # include in-memory public rooms
    for rid, r in rooms.items():
        if r.get("public", True):
            if not any(pr.get("id") == rid for pr in public_rooms):
                copy = dict(r)
                copy["id"] = rid
                public_rooms.append(copy)

    # sort by last_activity (fallback)
    public_rooms.sort(key=lambda x: x.get("last_activity", datetime.min), reverse=True)
    return render_template("discussion_index.html", rooms=public_rooms)

@app.route("/check_session", methods=["GET"])
@login_required
def check_session():
    return jsonify({"valid": True})

if __name__ == "__main__":
    cleanup_expired_rooms()
    
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    
    app.run(debug=debug_mode, host=host, port=port)
