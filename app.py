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
import docx
import PyPDF2
import pytesseract
from PIL import Image

from gnews import GNews

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

rooms = {}
cache = {}

# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(file_path):
    text = ""
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
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

# NEW AND IMPROVED: A pre-processing function to clean the text
def preprocess_text_for_quiz(text):
    # This regex removes lines that look like "Chapter X" or "Section Y"
    # It also handles variations like "CHAPTER 1", "section 2.", etc.
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        stripped_line = line.strip()
        # Regex to catch lines that are just "Chapter X" or "Section Y"
        if re.match(r'^(Chapter|Section)\s+\S+$', stripped_line, re.I):
            continue
        # NEW: Regex to catch lines that start with a 6-digit code followed by text
        if re.match(r'^\s*\d{6}\s+\S+', stripped_line):
            continue
        processed_lines.append(line)
    
    return '\n'.join(processed_lines)

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
    if not text:
        return None
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        return m.group(1)
    m = re.search(r"(\{(?:.|\n)*\})", text)
    if m:
        return m.group(1)
    return None

def quiz_to_uniform_schema(quiz_obj):
    out = {"questions": []}
    items = quiz_obj.get("questions") or quiz_obj.get("quiz") or []

    for q in items:
        question = str(q.get("question") or q.get("q") or "").strip()
        options = q.get("options") or q.get("choices") or []
        answer = str(q.get("answer") or q.get("correct") or q.get("correct_answer") or "").strip()

        if isinstance(options, dict):
            keys = ["A", "B", "C", "D"]
            options = [options.get(k, "").strip() for k in keys if options.get(k)]

        if isinstance(options, list):
            options = [str(o).strip() for o in options if o]
        else:
            options = []

        while len(options) < 4:
            options.append("N/A")
        options = options[:4]

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
- **Make questions based ONLY on the provided context. Focus on the core subject matter, not on chapters, sections, or document formatting.**
- Tailor the difficulty to a {grade} level.
- Focus on the {subject} section of the context.
- No prose, no explanation, no markdown, ONLY pure JSON.
Context (trimmed):
{context_text[:1500]}
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

    try:
        return quiz_to_uniform_schema(json.loads(raw))
    except Exception:
        pass

    jb = _extract_first_json_block(raw)
    if jb:
        try:
            return quiz_to_uniform_schema(json.loads(jb))
        except Exception:
            pass

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

def fetch_gnews_text(query, max_results=5, language='en', country='NG'):
    try:
        google_news = GNews(max_results=max_results, language=language, country=country)
        news_articles = google_news.get_news(query)

        if not news_articles:
            return "No recent articles found for this topic."

        context_text = ""
        for article in news_articles:
            context_text += f"Title: {article.get('title', '')}\n"
            context_text += f"Description: {article.get('description', '')}\n"
            context_text += f"Published Date: {article.get('published date', '')}\n\n"
        return context_text

    except Exception as e:
        logger.error(f"GNews fetch failed: {e}")
        return f"An error occurred while fetching news: {e}"

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
        if request.is_json:
            data = request.get_json(silent=True) or {}
            email = data.get("email", "").lower()
            password = data.get("password", "")
        else:
            email = request.form.get("email", "").lower()
            password = request.form.get("password", "")

        if email not in ALLOWED_USERS:
            return jsonify({"ok": False, "error": "Unauthorized email"}), 401

        try:
            api_key = os.getenv("FIREBASE_API_KEY")
            if not api_key:
                logger.error("FIREBASE_API_KEY not set")
                return jsonify({"ok": False, "error": "Auth service unavailable"}), 500

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
    try:
        data = request.get_json(force=True, silent=True) or {}
        grade = data.get("gl") or data.get("grade") or "GL10"
        subject = data.get("subject") or "General Knowledge"

        context_text = ""
        if subject.lower() in ["global politics", "current affairs"]:
            context_text = fetch_gnews_text("current affairs Nigeria politics")
        elif subject.lower() == "international bodies and acronyms":
            context_text = """
            What does FIFA stand for? Fédération Internationale de Football Association.
            What does FAO stand for? Food and Agriculture Organization.
            What does ECOWAS stand for? Economic Community of West African States.
            What does NAFDAC stand for? National Agency for Food and Drug Administration and Control.
            What does NSCDC stand for? Nigeria Security and Civil Defence Corps.
            What does WHO stand for? World Health Organization.
            What does UNICEF stand for? United Nations Children's Fund.
            What does AU stand for? African Union.
            What does NATO stand for? North Atlantic Treaty Organization.
            What does OPEC stand for? Organization of the Petroleum Exporting Countries.
            """
        else:
            context_text = f"Trial quiz for {subject} at grade {grade}"

        cache_key = generate_cache_key(f"{context_text}_{grade}_{subject}", 10, "freequiz")
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)

        quiz = call_gemini_for_quiz(context_text, subject, grade)
        cache_set(cache_key, quiz, ttl_minutes=10)
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
    try:
        if "document" not in request.files:
            return jsonify({"error": "No file uploaded (field: 'document')"}), 400

        file = request.files["document"]
        if not file or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400

        grade = request.form.get("grade", "GL10")
        subject = request.form.get("subject", "General Knowledge")
        filename = secure_filename(file.filename)

        suffix = os.path.splitext(filename)[1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        context_text = ""
        try:
            raw_text = extract_text_from_file(tmp_path)
            context_text = preprocess_text_for_quiz(raw_text)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_err:
                app.logger.warning(f"Could not delete temp file: {cleanup_err}")

        if not context_text:
            return jsonify({"error": "Could not extract text from uploaded file or text was too sparse"}), 400

        cache_key = generate_cache_key(f"{context_text}_{grade}_{subject}", 60, "genquiz")
        cached = cache_get(cache_key)
        if cached:
            log_quiz_activity(session["user_email"], "cache_hit", filename)
            return jsonify(cached)

        quiz = call_gemini_for_quiz(context_text, subject, grade)

        if not quiz.get("questions"):
            return jsonify({"error": "No questions generated"}), 500

        cache_set(cache_key, quiz, ttl_minutes=60)
        log_quiz_activity(session["user_email"], "generate_quiz", filename)
        return jsonify(quiz)

    except Exception as e:
        import traceback
        app.logger.error("Quiz generation failed: %s\n%s", str(e), traceback.format_exc())
        return jsonify({"error": "Quiz generation failed"}), 500

# --- NEW ROUTE: Quiz Scoring ---
@app.route("/submit_quiz", methods=["POST"])
@login_required
def submit_quiz():
    data = request.get_json()
    user_answers = data.get("answers", {})
    quiz_data = data.get("quiz_data", {})
    
    score = 0
    total_questions = len(quiz_data.get("questions", []))
    results = []

    for i, question in enumerate(quiz_data.get("questions", [])):
        question_id = str(i)
        user_answer = user_answers.get(question_id)
        correct_answer = question.get("answer")
        
        is_correct = (user_answer == correct_answer)
        if is_correct:
            score += 1
        
        results.append({
            "question": question.get("question"),
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct
        })

    log_quiz_activity(session["user_email"], "submit_quiz", f"Score: {score}/{total_questions}")
    return jsonify({
        "score": score,
        "total": total_questions,
        "results": results
    })

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
