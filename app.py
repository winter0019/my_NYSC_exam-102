import os
import uuid
import hashlib
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from loguru import logger
from dotenv import load_dotenv

import requests
import tempfile
import docx
import PyPDF2
import pytesseract
import fitz  # PyMuPDF
from PIL import Image

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- Load Environment ---
load_dotenv()

# Configure Google Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- Flask App Setup ---
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
CORS(app)

app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")

# --- Rate Limiter ---
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per day", "20 per hour"])

# --- Logger ---
logger.add("logs/app_{time}.log", rotation="1 day", level="INFO")

# --- Firebase Setup ---
db = None
try:
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if firebase_json:
        cred_dict = eval(firebase_json) if isinstance(firebase_json, str) else firebase_json
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("Firebase initialized successfully")
except Exception as e:
    logger.warning(f"Firebase not initialized: {e}")

# --- Constants ---
ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg"}
ALLOWED_EMAILS = {"admin@nysc.gov.ng", "staff@nysc.gov.ng"}

rooms = {}  # in-memory fallback
cache = {}

# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path):
    text = ""
    ext = file_path.rsplit(".", 1)[1].lower()
    try:
        if ext == "pdf":
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
        elif ext == "docx":
            doc = docx.Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext in {"png", "jpg", "jpeg"}:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
    except Exception as e:
        logger.error(f"File extraction failed: {e}")
    return text.strip()

def generate_cache_key(base, ttl_minutes, prefix=""):
    h = hashlib.md5(base.encode()).hexdigest()
    return f"{prefix}_{h}_{ttl_minutes}"

def cache_set(key, value, ttl_minutes=5):
    cache[key] = {"value": value, "expires": datetime.now() + timedelta(minutes=ttl_minutes)}

def cache_get(key):
    if key in cache:
        if datetime.now() < cache[key]["expires"]:
            return cache[key]["value"]
        del cache[key]
    return None

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def log_quiz_activity(user, action, details=""):
    logger.info(f"{user} | {action} | {details}")

def cleanup_expired_rooms():
    now = datetime.now()
    expired = [rid for rid, r in rooms.items() if (now - r["last_activity"]) > timedelta(hours=24)]
    for rid in expired:
        del rooms[rid]

@app.before_request
def before_request():
    cleanup_expired_rooms()

# --- Routes ---
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").lower()
        password = request.form.get("password", "")
        if email not in ALLOWED_EMAILS:
            return render_template("login.html", error="Unauthorized email")

        try:
            resp = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": os.getenv("FIREBASE_API_KEY")},
                json={"email": email, "password": password, "returnSecureToken": True},
            )
            if resp.status_code == 200:
                session["user_email"] = email
                return redirect(url_for("dashboard"))
            return render_template("login.html", error="Invalid credentials")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return render_template("login.html", error="Authentication error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = session["user_email"]
    if user == "admin@nysc.gov.ng":
        return render_template("admin_dashboard.html", email=user)
    return render_template("dashboard.html", email=user)

# --- Free Trial Quiz ---
@app.route("/free_trial_quiz")
@login_required
def free_trial_quiz():
    return render_template("free_trial_quiz.html", email=session["user_email"])

@app.route("/generate_free_quiz", methods=["POST"])
@login_required
def generate_free_quiz():
    try:
        data = request.get_json()
        grade = data.get("gl")
        subject = data.get("subject")

        prompt = f"Generate 5 multiple choice questions with 4 options each (A-D), mark correct answers. Topic: {subject}, Level: {grade}."

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            prompt,
            safety_settings={HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE}
        )

        quiz_text = response.text
        questions = []
        for block in quiz_text.split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                q = {"question": lines[0], "options": lines[1:], "answer": lines[-1]}
                questions.append(q)

        discussions = [f"What is the impact of {subject} on daily NYSC operations?"]

        log_quiz_activity(session["user_email"], "free_trial", f"GL={grade}, Sub={subject}")
        return jsonify({"quiz": questions, "discussions": [{"q": d} for d in discussions]})
    except Exception as e:
        logger.error(f"Free quiz error: {e}")
        return jsonify({"error": "Quiz generation failed"})

# --- Document Upload Quiz ---
@app.route("/generate_doc_quiz", methods=["POST"])
@login_required
def generate_doc_quiz():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file = request.files["file"]
        if not file or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        grade = request.form.get("gl", "GL10")
        subject = request.form.get("subject", "General Knowledge")

        filename = secure_filename(file.filename)
        temp = tempfile.NamedTemporaryFile(delete=False)
        file.save(temp.name)

        text_main = extract_text_from_file(temp.name)
        text_past = request.form.get("past_questions", "")
        os.unlink(temp.name)

        if not text_main.strip():
            return jsonify({"error": "File text extraction failed"}), 400

        cache_key = generate_cache_key(f"{text_main}_{text_past}_{grade}_{subject}", 5, "docquiz")
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

        prompt = f"""
        Create 5 multiple-choice questions (A-D) with correct answers.
        Base them on this text:
        {text_main[:1500]}
        Past Qs: {text_past}
        Context: Subject {subject}, Grade {grade}.
        """

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        quiz_text = response.text

        questions = []
        for block in quiz_text.split("\n\n"):
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                q = {"question": lines[0], "options": lines[1:], "answer": lines[-1]}
                questions.append(q)

        result = {"quiz": questions, "discussions": [{"q": f"Debate implications of {subject}"}]}
        cache_set(cache_key, result, 5)
        log_quiz_activity(session["user_email"], "doc_quiz", filename)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Doc quiz error: {e}")
        return jsonify({"error": "Quiz generation failed"})

# --- Discussion Rooms ---
@app.route("/discussion", methods=["GET", "POST"])
@login_required
def discussion_index():
    return render_template("discussion.html", email=session["user_email"])

@app.route("/discussion/<room_id>", methods=["GET"])
@login_required
def join_discussion(room_id):
    if db:
        doc = db.collection("discussion_rooms").document(room_id).get()
        if doc.exists:
            return render_template("room.html", room_id=room_id, email=session["user_email"])
    if room_id in rooms:
        return render_template("room.html", room_id=room_id, email=session["user_email"])
    return jsonify({"error": "Room not found"}), 404

@app.route("/create_room", methods=["POST"])
@login_required
def create_room():
    data = request.get_json()
    question = data.get("question", "General topic")
    room_id = str(uuid.uuid4())
    room_data = {
        "question": question,
        "created_by": session["user_email"],
        "messages": [],
        "created_at": datetime.now(),
        "last_activity": datetime.now()
    }
    if db:
        db.collection("discussion_rooms").document(room_id).set(room_data)
    else:
        rooms[room_id] = room_data
    return jsonify({"room_id": room_id})

@app.route("/room/<room_id>/messages", methods=["GET", "POST"])
@login_required
def handle_messages(room_id):
    if request.method == "POST":
        data = request.get_json()
        message = {"user": session["user_email"], "text": data.get("text", ""), "time": datetime.now()}
        if db:
            db.collection("discussion_rooms").document(room_id).update({
                "messages": firestore.ArrayUnion([message]),
                "last_activity": firestore.SERVER_TIMESTAMP
            })
        else:
            if room_id not in rooms:
                return jsonify({"error": "Room not found"}), 404
            rooms[room_id]["messages"].append(message)
            rooms[room_id]["last_activity"] = datetime.now()
        return jsonify({"success": True})

    if db:
        doc = db.collection("discussion_rooms").document(room_id).get()
        if doc.exists:
            return jsonify(doc.to_dict().get("messages", []))
    elif room_id in rooms:
        return jsonify(rooms[room_id].get("messages", []))
    return jsonify([])

@app.route("/summarize/<room_id>", methods=["POST"])
@login_required
@limiter.limit("3 per hour")
def summarize_room(room_id):
    try:
        room = None
        messages = []
        if db:
            doc = db.collection("discussion_rooms").document(room_id).get()
            if doc.exists:
                room = doc.to_dict()
                messages = room.get("messages", [])
        if not room:
            room = rooms.get(room_id)
            messages = room.get("messages", []) if room else []

        if not room:
            return jsonify({"error": "Room not found"}), 404
        if len(messages) < 3:
            return jsonify({"error": "Not enough messages"}), 400

        discussion_text = "\n".join([f"{m['user']}: {m['text']}" for m in messages])
        prompt = f"Summarize discussion on '{room['question']}'.\n\n{discussion_text}"

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        summary = response.text.strip()

        if db:
            db.collection("discussion_rooms").document(room_id).update({
                "final_answer": summary,
                "last_activity": firestore.SERVER_TIMESTAMP
            })
        else:
            room["final_answer"] = summary
            room["last_activity"] = datetime.now()
        return jsonify({"summary": summary})
    except Exception as e:
        logger.error(f"Summarize error: {e}")
        return jsonify({"error": "Summarization failed"}), 500

# --- Run ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
