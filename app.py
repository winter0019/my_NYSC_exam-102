import os
import re
import json
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
import tempfile, os
from werkzeug.utils import secure_filename
import docx
import PyPDF2
import pytesseract
from PIL import Image

# Firebase (admin SDK – optional, used when FIREBASE_SERVICE_ACCOUNT is present)
import firebase_admin
from firebase_admin import credentials, firestore, auth

# --- Load Environment ---
load_dotenv()

# --- Configure Google Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")
genai.configure(api_key=GEMINI_API_KEY)

# --- Flask App Setup ---
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")

# --- Rate Limiter ---
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per day", "20 per hour"])

# --- Logger ---
logger.add("logs/app_{time}.log", rotation="1 day", level="INFO")

# --- Firebase Setup (optional) ---
db = None
try:
    firebase_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if firebase_json:
        # NOTE: prefer json.loads over eval for safety
        cred_dict = json.loads(firebase_json) if isinstance(firebase_json, str) else firebase_json
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("Firebase initialized successfully")
    else:
        logger.info("FIREBASE_SERVICE_ACCOUNT not set; using in-memory room storage only.")
except Exception as e:
    logger.warning(f"Firebase not initialized: {e}")

# --- Constants ---
ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg"}
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
ALLOWED_USERS = {email.lower() for email in ALLOWED_USERS}

rooms = {}  # in-memory fallback when Firestore isn't available
cache = {}

# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path):
    text = ""
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")  # safer extension handling
    try:
        if ext == "pdf":
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
        elif ext == "docx":
            document = docx.Document(file_path)
            text = "\n".join(p.text for p in document.paragraphs)
        elif ext in {"png", "jpg", "jpeg"}:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    except Exception as e:
        logger.error(f"File extraction failed: {e}")
    return (text or "").strip()

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

# --- Robust Gemini quiz parsing ---
def _extract_first_json_block(text: str):
    """
    Try to pull the first JSON block from a possibly-markdown response.
    """
    if not text:
        return None
    # ```json ... ``` fenced
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        return m.group(1)
    # Any {...} top-level looking JSON
    m = re.search(r"(\{(?:.|\n)*\})", text)
    if m:
        return m.group(1)
    return None

def quiz_to_uniform_schema(quiz_obj):
    """
    Normalize quiz data into a safe schema:
    { "questions": [ { "question": str, "options": [str, str, str, str], "answer": str } ] }
    """
    out = {"questions": []}
    items = quiz_obj.get("questions") or quiz_obj.get("quiz") or []

    for q in items:
        question = str(q.get("question") or q.get("q") or "").strip()
        options = q.get("options") or q.get("choices") or []
        answer = str(q.get("answer") or q.get("correct") or q.get("correct_answer") or "").strip()

        # Convert dict → list in A–D order
        if isinstance(options, dict):
            keys = ["A", "B", "C", "D"]
            options = [options.get(k, "").strip() for k in keys if options.get(k)]

        # Clean list
        if isinstance(options, list):
            options = [str(o).strip() for o in options if o]
        else:
            options = []

        # Guarantee exactly 4 options (pad with N/A or trim)
        while len(options) < 4:
            options.append("N/A")
        options = options[:4]

        # Validate answer: must be inside options
        if answer not in options:
            answer = ""

        if question:
            out["questions"].append({
                "question": question,
                "options": options,
                "answer": answer
            })

    return out


def call_gemini_for_quiz(context_text: str, subject: str, grade: str):
    """
    Ask Gemini to return strict JSON for MCQs. Falls back to best-effort parse.
    """
    system_prompt = f"""
You are a question generator for NYSC exam prep.
Return STRICT JSON ONLY with this shape:

{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "answer": "the correct option text EXACTLY as shown in options"
    }}
  ]
}}

Rules:
- 5 questions.
- 4 options each.
- Options should be concise.
- Make questions based ONLY on the provided context (if weak, fall back to subject knowledge for that grade).
- No prose, no explanation, no markdown, ONLY pure JSON.
Context (trimmed):
{context_text[:1500]}

Subject: {subject}
Grade: {grade}
"""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(
        system_prompt,
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )

    raw = (response.text or "").strip()

    # Try strict JSON parse
    try:
        return quiz_to_uniform_schema(json.loads(raw))
    except Exception:
        pass

    # Try extracting a JSON block
    jb = _extract_first_json_block(raw)
    if jb:
        try:
            return quiz_to_uniform_schema(json.loads(jb))
        except Exception:
            pass

    # Last resort: naive parse (Q + A–D lines)
    questions = []
    blocks = re.split(r"\n\s*\n", raw)
    for b in blocks:
        lines = [ln.strip("- ").strip() for ln in b.split("\n") if ln.strip()]
        if len(lines) >= 5:
            q = lines[0]
            opts = []
            for ln in lines[1:5]:
                m = re.match(r"^[A-D][\).:\-]\s*(.+)$", ln, flags=re.I)
                opts.append(m.group(1) if m else ln)
            while len(opts) < 4:
                opts.append("N/A")
            questions.append({"question": q, "options": opts[:4], "answer": ""})

    return {"questions": questions[:5]}

# --- Routes ---
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/health")
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat() + "Z"})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Extract request data
        if request.is_json:
            data = request.get_json(silent=True) or {}
            email = data.get("email", "").lower()
            password = data.get("password", "")
        else:
            email = request.form.get("email", "").lower()
            password = request.form.get("password", "")

        # Check allowed users
        if email not in ALLOWED_USERS:
            return jsonify({"ok": False, "error": "Unauthorized email"}), 401

        try:
            api_key = os.getenv("FIREBASE_API_KEY")
            if not api_key:
                logger.error("FIREBASE_API_KEY not set")
                return jsonify({"ok": False, "error": "Auth service unavailable"}), 500

            # Call Firebase Auth REST API
            resp = requests.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": api_key},
                json={"email": email, "password": password, "returnSecureToken": True},
                timeout=15,
            )

            if resp.status_code == 200:
                session["user_email"] = email
                role = "admin" if email == "admin@nysc.gov.ng" else "user"
                return jsonify({"ok": True, "role": role})
            else:
                return jsonify({"ok": False, "error": "Invalid credentials"}), 401

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return jsonify({"ok": False, "error": "Authentication error"}), 500

    # GET request → return login page
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


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
    """
    Generate a free trial quiz without requiring a document upload.
    Input (JSON):
      - grade
      - subject
    Output:
      { "questions": [ { "question": str, "options": [..], "answer": str } ] }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        grade = data.get("gl") or data.get("grade") or "GL10"
        subject = data.get("subject") or "General Knowledge"

        # Keep consistent with generate_quiz: context_text = source, not a system prompt
        context_text = f"Trial quiz for {subject} at grade {grade}"

        cache_key = generate_cache_key(f"{context_text}_{grade}_{subject}", 10, "freequiz")
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

        quiz = call_gemini_for_quiz(context_text, subject, grade)
        cache_set(cache_key, quiz, 10)
        log_quiz_activity(session["user_email"], "free_trial", f"GL={grade}, Sub={subject}")
        return jsonify(quiz)

    except Exception as e:
        logger.error(f"Free quiz error: {e}")
        return jsonify({"error": "Quiz generation failed"}), 500

@app.route("/quiz")
@login_required
def quiz():
    return render_template("quiz.html", email=session["user_email"])


# --- Document Upload Quiz ---
@app.route("/generate_quiz", methods=["POST"])
@login_required
def generate_quiz():
    """
    Handle document upload, extract text, and generate quiz with Gemini.
    Responds with:
      { "questions": [ { "question": str, "options": [..], "answer": str } ] }
    """
    try:
        # 1. Check uploaded file
        if "document" not in request.files:
            return jsonify({"error": "No file uploaded (field: 'document')"}), 400

        file = request.files["document"]
        if not file or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        grade = request.form.get("grade", "GL10")
        subject = request.form.get("subject", "General Knowledge")

        # 2. Save temp file with correct extension
        filename = secure_filename(file.filename)
        suffix = os.path.splitext(filename)[1] or ".pdf"  # fallback if no extension

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        # 3. Extract text from file
        try:
            context_text = extract_text_from_file(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                app.logger.warning(f"Could not delete temp file: {cleanup_err}")

        if not context_text:
            return jsonify({"error": "Could not extract text from uploaded file"}), 400

        # 4. Call Gemini with cache
        cache_key = generate_cache_key(f"{context_text}_{grade}_{subject}", 10, "genquiz")
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

        quiz = call_gemini_for_quiz(context_text, subject, grade)

        # 5. Log quiz for debugging
        app.logger.info("Generated quiz: %s", quiz)

        if not quiz.get("questions"):
            return jsonify({"error": "No questions generated"}), 500

        # 6. Cache and return
        cache_set(cache_key, quiz, ttl=3600)
        return jsonify(quiz)

    except Exception as e:
        app.logger.error(f"Quiz generation failed: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


        cache_set(cache_key, quiz, 10)
        log_quiz_activity(session["user_email"], "generate_quiz", filename)
        return jsonify(quiz)

    except Exception as e:
        import traceback
        app.logger.error("Quiz generation failed: %s\n%s", str(e), traceback.format_exc())
        return jsonify({"error": "Quiz generation failed"}), 500


        # Normalize each question
        safe_questions = []
        for q in quiz["questions"]:
            question = q.get("question", "").strip()
            options = q.get("options", []) or []
            answer = q.get("answer", "").strip()

            # Ensure at least 4 options (pad with N/A if missing)
            if isinstance(options, dict):
                keys = ["A", "B", "C", "D"]
                options = [options.get(k) for k in keys if options.get(k)]
            while len(options) < 4:
                options.append("N/A")
            options = options[:4]

            if question and options:
                safe_questions.append({
                    "question": question,
                    "options": options,
                    "answer": answer if answer in options else ""
                })

        if not safe_questions:
            logger.error("Quiz generation produced no valid questions")
            return jsonify({"error": "Quiz generation failed (empty quiz)"}), 500

        final_quiz = {"questions": safe_questions}

        # Cache + log
        cache_set(cache_key, final_quiz, 10)
        log_quiz_activity(session["user_email"], "generate_quiz", filename)

        return jsonify(final_quiz)

    except Exception as e:
        logger.error(f"/generate_quiz error: {e}")
        return jsonify({"error": "Quiz generation failed"}), 500

        # Normalize each question
        safe_questions = []
        for q in quiz["questions"]:
            question = q.get("question", "").strip()
            options = q.get("options", []) or []
            answer = q.get("answer", "").strip()

            # Ensure at least 4 options (pad with N/A if missing)
            if isinstance(options, dict):
                keys = ["A", "B", "C", "D"]
                options = [options.get(k) for k in keys if options.get(k)]
            while len(options) < 4:
                options.append("N/A")
            options = options[:4]

            if question and options:
                safe_questions.append({
                    "question": question,
                    "options": options,
                    "answer": answer if answer in options else ""
                })

        if not safe_questions:
            logger.error("Quiz generation produced no valid questions")
            return jsonify({"error": "Quiz generation failed (empty quiz)"}), 500

        final_quiz = {"questions": safe_questions}

        # Cache + log
        cache_set(cache_key, final_quiz, 10)
        log_quiz_activity(session["user_email"], "generate_quiz", filename)

        return jsonify(final_quiz)

    except Exception as e:
        logger.error(f"/generate_quiz error: {e}")
        return jsonify({"error": "Quiz generation failed"}), 500


# --- Discussion (template-driven pages) ---
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
    data = request.get_json(force=True, silent=True) or {}
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
        data = request.get_json(force=True, silent=True) or {}
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
        summary = (response.text or "").strip()

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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
















