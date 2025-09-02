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
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core import exceptions
import PyPDF2
import requests
import pytesseract
from PIL import Image
import fitz # PyMuPDF for better PDF text extraction
import firebase_admin

# Try to import optional dependencies
try:
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
load_dotenv()
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
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            logger.info("Firebase initialized successfully")
        else:
            logger.warning("Firebase credentials file not found. Firebase features disabled.")
    except Exception as e:
        logger.warning(f"Firebase init failed: {e}")
        db = None
else:
    logger.warning("Firebase not available. Some features will be disabled.")

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")

# --- Helper Functions ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_email" not in session:
            return jsonify({"error": "Authentication required"}), 401
        
        email = session["user_email"]
        session_id = session.get("session_id")
        if active_sessions.get(email) != session_id:
            session.clear()
            return jsonify({"error": "Session expired. Please login again."}), 401
            
        return f(*args, **kwargs)
    return decorated_function

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_grade(grade):
    return grade in ["GL8", "GL10", "GL12", "GL14", "GL16"]

def validate_file_extension(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def cleanup_expired_rooms():
    """Remove rooms that haven't been active for more than 24 hours"""
    current_time = datetime.now()
    expired_rooms = []
    
    for room_id, room_data in rooms.items():
        if 'last_activity' in room_data and current_time - room_data['last_activity'] > timedelta(hours=24):
            expired_rooms.append(room_id)
    
    for room_id in expired_rooms:
        del rooms[room_id]
        logger.info(f"Cleaned up expired room: {room_id}")

def fetch_latest_news():
    try:
        ng_news = requests.get(
            f"https://gnews.io/api/v4/top-headlines?lang=en&country=ng&max=10&apikey={GNEWS_API_KEY}",
            timeout=10
        ).json().get("articles", [])
        world_news = requests.get(
            f"https://gnews.io/api/v4/top-headlines?lang=en&country=us&max=10&apikey={GNEWS_API_KEY}",
            timeout=10
        ).json().get("articles", [])
        headlines = [a["title"] for a in ng_news + world_news if "title" in a]
        return "\n".join(headlines[:15]) or "No live news available."
    except Exception as e:
        logger.error(f"News fetch error: {e}")
        return "No live news available."

def extract_text_from_docx(file_stream) -> str:
    try:
        doc = Document(file_stream)
        text = "\n".join([p.text for p in doc.paragraphs])
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception as e:
        logger.error(f"Error extracting DOCX: {e}")
        return ""

def extract_text_from_pdf(file_stream) -> str:
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception as e:
        logger.error(f"Error extracting PDF: {e}")
        return ""
    
def extract_text_from_image(file_path):
    """Extract text from image using Tesseract OCR"""
    try:
        text = pytesseract.image_to_string(Image.open(file_path))
        return text
    except Exception as e:
        logger.error(f"Error extracting text from image: {e}")
        return ""

def extract_text_from_pdf_fitz(file_stream) -> str:
    """Extract text from PDF using PyMuPDF (fallback if PyPDF2 fails)"""
    try:
        doc = fitz.open(stream=file_stream.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text") or ""
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting PDF with fitz: {e}")
        return ""

def json_hard_extract(s: str):
    try:
        return json.loads(s)
    except Exception:
        m_obj = re.search(r"\{(?:[^{}]|(?R))*\}", s, re.S)
        m_arr = re.search(r"\[(?:[^\[\]]|(?R))*\]", s, re.S)
        candidate = None
        if m_obj and m_arr:
            candidate = m_obj.group(0) if len(m_obj.group(0)) >= len(m_arr.group(0)) else m_arr.group(0)
        elif m_obj:
            candidate = m_obj.group(0)
        elif m_arr:
            candidate = m_arr.group(0)
        if candidate:
            try:
                return json.loads(candidate)
            except:
                logger.warning(f"Failed to parse extracted JSON: {candidate}")
                raise ValueError("Could not extract valid JSON from model output.")
        raise ValueError("Could not extract valid JSON from model output.")

def coerce_schema(data: dict):
    if not isinstance(data, dict):
        data = {}

    quiz = data.get("quiz") or []
    discussions = data.get("discussions") or []

    norm_quiz = []
    seen_questions = set()

    for q in quiz:
        if not isinstance(q, dict):
            continue
        question = (q.get("question") or "").strip()
        if not question or question in seen_questions:
            continue
        seen_questions.add(question)
        correct = (q.get("correct") or q.get("answer") or "").strip()
        options = q.get("options") or []
        options = [o.strip() for o in options if o.strip() and o.strip() != correct][:3]
        options.append(correct if correct else "Option A")
        options = list(dict.fromkeys(options))
        while len(options) < 4:
            options.append(f"Option {chr(65+len(options))}")
        norm_quiz.append({
            "question": question,
            "options": options[:4],
            "correct": correct if correct else options[0]
        })

    while len(norm_quiz) < 5:
        idx = len(norm_quiz)
        norm_quiz.append({
            "question": f"Placeholder question {idx+1}.",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct": "Option A"
        })

    norm_disc = []
    for d in discussions:
        if isinstance(d, dict) and "q" in d and isinstance(d["q"], str) and d["q"].strip():
            qtext = d["q"].strip()
            if qtext not in [x["q"] for x in norm_disc]:
                norm_disc.append({"q": qtext})
    if not norm_disc:
        norm_disc = [{"q": "What are the practical challenges in applying disciplinary procedures fairly?"}]
    norm_disc = norm_disc[:2]

    return {"quiz": norm_quiz[:5], "discussions": norm_disc}

def log_quiz_activity(user_email, quiz_type, subject, score=None):
    """Log quiz activity for analytics"""
    try:
        if db:
            quiz_data = {
                'user_email': user_email,
                'quiz_type': quiz_type,
                'subject': subject,
                'timestamp': datetime.now(),
                'score': score
            }
            db.collection('quiz_activities').add(quiz_data)
            logger.info(f"Logged quiz activity for {user_email}")
    except Exception as e:
        logger.error(f"Failed to log quiz activity: {e}", exc_info=True)

def generate_cache_key(document_text, num_questions, quiz_type):
    """Generate a unique cache key based on document content and quiz parameters"""
    key_string = f"{document_text}_{num_questions}_{quiz_type}"
    return hashlib.md5(key_string.encode()).hexdigest()

def get_cached_quiz(cache_key):
    """Retrieve a cached quiz from Firestore if it exists and is still valid"""
    if not db:
        logger.info("Firestore not available, skipping cache")
        return None
        
    try:
        cache_ref = db.collection('quiz_cache').document(cache_key)
        cached_data = cache_ref.get()
        
        if cached_data.exists:
            cache_data = cached_data.to_dict()
            cache_time = cache_data['timestamp']
            if datetime.now() - cache_time.replace(tzinfo=None) < timedelta(hours=24):
                logger.info(f"Returning cached quiz for key: {cache_key}")
                return cache_data['quiz_data']
            else:
                logger.info("Cache expired, generating new quiz")
        else:
            logger.info("No cache found, generating new quiz")
    except Exception as e:
        logger.error(f"Error accessing cache: {e}", exc_info=True)
    
    return None

def store_quiz_in_cache(cache_key, quiz_data):
    """Store a quiz in Firestore cache"""
    if not db:
        return
        
    try:
        cache_ref = db.collection('quiz_cache').document(cache_key)
        cache_ref.set({
            'quiz_data': quiz_data,
            'timestamp': datetime.now(),
            'parameters': {
                'num_questions': len(quiz_data.get('quiz', [])),
                'quiz_type': 'document'
            }
        })
        logger.info(f"Stored quiz in cache with key: {cache_key}")
    except Exception as e:
        logger.error(f"Error storing quiz in cache: {e}", exc_info=True)

def create_discussion_rooms(discussions, creator_email=None):
    """Helper to create discussion rooms in both Firestore and memory"""
    created_discussions = []
    
    # Get creator email
    if creator_email is None:
        try:
            from flask import session
            creator_email = session.get("user_email", "system@nyscexamprep.com")
        except RuntimeError:
            creator_email = "system@nyscexamprep.com"
    
    for d in discussions:
        room_id = str(uuid.uuid4())
        room_data = {
            "question": d["q"], 
            "messages": [], 
            "final_answer": None,
            "created_by": creator_email,
            "created_at": datetime.now(),
            "last_activity": datetime.now(),
            "public": True,
            "participants": []
        }
        
        # Store in memory
        rooms[room_id] = room_data
        
        # Also persist to Firestore if available
        if db:
            try:
                db.collection('discussion_rooms').document(room_id).set({
                    **room_data,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "last_activity": firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                logger.warning(f"Failed to persist discussion room to Firestore: {e}")
        
        created_discussions.append({"id": room_id, "q": d["q"]})
    
    return created_discussions

def fetch_user_history(email, limit=10):
    """Fetch recent user quiz history from Firestore"""
    if not db:
        return []
    try:
        user_ref = db.collection('users').document(email).collection('history')
        query = user_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Failed to fetch user history for {email}: {e}", exc_info=True)
        return []

# --- Middleware: check active session ---
@app.before_request
def enforce_single_session():
    if request.endpoint in ['login', 'signup', 'static', 'login_page', 'favicon', 'check_session', 'logout']:
        return
        
    if "user_email" in session:
        email = session["user_email"]
        session_id = session.get("session_id")
        if active_sessions.get(email) != session_id:
            session.clear()
            return jsonify({"error": "Session expired. Please login again."}), 401

# Add this with your other helper functions
@app.template_filter('format_datetime')
def format_datetime(value):
    """Format a datetime object or string for display"""
    if not value:
        return "N/A"
    
    # Handle string timestamps
    if isinstance(value, str):
        try:
            # Try to parse ISO format
            if 'T' in value:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            else:
                # Try other common formats
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except (ValueError, AttributeError, TypeError):
            # If parsing fails, return the original string
            return value
    
    # Handle datetime objects
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    
    # Handle other types (like Firestore timestamps)
    if hasattr(value, 'strftime'):
        try:
            return value.strftime('%Y-%m-%d %H:%M')
        except:
            pass
    
    return str(value)

# --- Routes ---
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

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
            
            # Generate session ID
            current_session_id = str(uuid.uuid4())
            session["user_email"] = email
            session["session_id"] = current_session_id
            session["user_id"] = user_data.get("localId", "")
            
            # Store active session
            active_sessions[email] = current_session_id
            
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
        
        current_session_id = str(uuid.uuid4())
        session["user_email"] = email
        session["user_grade"] = grade
        session["session_id"] = current_session_id
        session["user_id"] = user_data.get("localId", "")
        
        active_sessions[email] = current_session_id
        
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
    if "user_email" in session:
        email = session["user_email"]
        active_sessions.pop(email, None)
        logger.info(f"User logged out: {email}")
    session.clear()
    return redirect(url_for("login_page"))

@app.route("/dashboard")
@login_required
def dashboard():
    email = session["user_email"]
    
    admin_email = "dangalan20@gmail.com"
    is_admin = email == admin_email

    if is_admin:
        users_data = []
        try:
            if db:
                users_ref = db.collection("users")
                users_docs = users_ref.stream()
                
                for user_doc in users_docs:
                    user_info = user_doc.to_dict()
                    user_email = user_info.get('email')
                    
                    if user_email:
                        history = fetch_user_history(user_email, limit=10)
                        
                        # Add is_admin flag to history items for consistent rendering
                        for item in history:
                            item['is_admin'] = is_admin
                            
                        user_info['history'] = history
                        users_data.append(user_info)

        except Exception as e:
            logger.error(f"Error fetching users overview: {e}")
            users_data = []
        return render_template("admin_dashboard.html", users_data=users_data, email=email)
    else:
        history = []
        try:
            history = fetch_user_history(email, limit=10)
        except Exception as e:
            logger.error(f"Error fetching history for {email}: {e}")

        return render_template("dashboard.html", email=email, history=history, grade=session.get("user_grade", "GL10"))

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
                    main_file.seek(0) # Reset stream position
                    text_main = extract_text_from_pdf_fitz(main_file)
            else:  # images
                text_main = extract_text_from_image(main_file)

        if past_file and past_file.filename:
            if past_file.filename.endswith(".docx"):
                text_past = extract_text_from_docx(past_file)
            elif past_file.filename.endswith(".pdf"):
                text_past = extract_text_from_pdf(past_file)
                if not text_past:
                    past_file.seek(0) # Reset stream position
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
        if "user_email" not in session:
            return jsonify({"authenticated": False, "error": "No active session"}), 401
        
        email = session["user_email"]
        session_id = session.get("session_id")
        
        if active_sessions.get(email) != session_id:
            session.clear()
            return jsonify({"authenticated": False, "error": "Session expired"}), 401
        
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
@limiter.limit("200 per hour")
def get_messages(room_id):
    try:
        messages = []
        room_data = rooms.get(room_id)
        if db and room_data:
            room_ref = db.collection('discussion_rooms').document(room_id)
            room_doc = room_ref.get()
            if room_doc.exists:
                room_data = room_doc.to_dict()
                messages = room_data.get('messages', [])
        
        if not messages:
            # Fallback to in-memory messages if Firestore is unavailable or empty
            messages = rooms.get(room_id, {}).get("messages", [])
        
        # Convert Firestore timestamps to a format jsonify can handle
        formatted_messages = []
        for msg in messages:
            msg_copy = msg.copy()
            if isinstance(msg_copy.get('timestamp'), datetime):
                msg_copy['timestamp'] = msg_copy['timestamp'].isoformat()
            formatted_messages.append(msg_copy)

        return jsonify({"messages": formatted_messages}), 200
    except Exception as e:
        logger.error(f"Error getting messages for room {room_id}: {e}")
        return jsonify({"error": "Failed to retrieve messages"}), 500

@app.route('/send_message', methods=['POST'])
@login_required
@limiter.limit("100 per hour")
def send_message():
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        message_text = data.get('message')
        email = session.get('user_email')
        
        if not room_id or not message_text or not email:
            return jsonify({"error": "Missing data"}), 400
            
        new_message = {
            "user": email,
            "text": message_text,
            "timestamp": datetime.now()
        }
        
        # In-memory update
        if room_id in rooms:
            rooms[room_id]["messages"].append(new_message)
            rooms[room_id]["last_activity"] = datetime.now()
        
        # Firestore update
        if db:
            room_ref = db.collection('discussion_rooms').document(room_id)
            room_ref.update({
                'messages': firestore.ArrayUnion([new_message]),
                'last_activity': firestore.SERVER_TIMESTAMP
            })
            
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        return jsonify({"error": "Failed to send message"}), 500

@app.route('/list_rooms')
@login_required
@limiter.limit("20 per hour")
def list_rooms():
    try:
        rooms_list = []
        # Try to get from Firestore first
        if db:
            rooms_ref = db.collection('discussion_rooms')
            docs = rooms_ref.stream()
            for doc in docs:
                room = doc.to_dict()
                room['id'] = doc.id
                rooms_list.append(room)
        
        if not rooms_list:
            # Fallback to in-memory rooms
            for room_id, room_data in rooms.items():
                room_data['id'] = room_id
                rooms_list.append(room_data)
        
        return jsonify({"rooms": rooms_list}), 200
    except Exception as e:
        logger.error(f"Error listing rooms: {e}", exc_info=True)
        return jsonify({"error": "Failed to list rooms"}), 500

@app.route('/submit_quiz', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def submit_quiz():
    try:
        data = request.get_json()
        quiz = data.get('quiz')
        user_answers = data.get('answers')
        quiz_type = data.get('quiz_type')
        subject = data.get('subject')

        score = 0
        if quiz and user_answers:
            for question in quiz:
                q_id = question.get('question')
                correct_answer = question.get('correct')
                user_answer = user_answers.get(q_id)
                
                if user_answer and user_answer.strip().lower() == correct_answer.strip().lower():
                    score += 1
        
        # Log the quiz result
        log_quiz_activity(session["user_email"], quiz_type, subject, score)
        
        return jsonify({"score": score}), 200
    
    except Exception as e:
        logger.error(f"Error submitting quiz: {e}", exc_info=True)
        return jsonify({"error": "Failed to submit quiz"}), 500


if __name__ == "__main__":
    if os.getenv("FLASK_ENV") == "development":
        app.run(debug=True, host="0.0.0.0", port=5000)
    else:
        app.run()
