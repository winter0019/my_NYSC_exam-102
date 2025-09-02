<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NYSC Exam Dashboard</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
  <style>
    :root {
      --primary: #3498db;
      --secondary: #2c3e50;
      --accent: #e74c3c;
      --light: #ecf0f1;
      --dark: #2c3e50;
      --success: #2ecc71;
      --warning: #f39c12;
      --danger: #e74c3c;
      --shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
      --transition: all 0.3s ease;
    }
    
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }
    
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
      color: #333;
      line-height: 1.6;
      min-height: 100vh;
    }
    
    .container {
      width: 90%;
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
    }
    
    header {
      background: var(--secondary);
      color: white;
      padding: 15px 0;
      border-radius: 10px;
      margin-bottom: 30px;
      box-shadow: var(--shadow);
    }
    
    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 20px;
    }
    
    .logo {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .logo i {
      font-size: 2rem;
      color: var(--primary);
    }
    
    .user-info {
      text-align: right;
    }
    
    .logout-btn {
      background: var(--accent);
      color: white;
      border: none;
      padding: 8px 15px;
      border-radius: 5px;
      cursor: pointer;
      transition: var(--transition);
    }
    
    .logout-btn:hover {
      background: #c0392b;
    }
    
    .dashboard-title {
      text-align: center;
      margin: 20px 0;
      color: var(--dark);
      position: relative;
    }
    
    .dashboard-title:after {
      content: '';
      display: block;
      width: 100px;
      height: 4px;
      background: var(--primary);
      margin: 10px auto;
      border-radius: 2px;
    }
    
    .card-container {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 25px;
      margin-bottom: 30px;
    }
    
    .card {
      background: white;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: var(--shadow);
      transition: var(--transition);
    }
    
    .card:hover {
      transform: translateY(-5px);
      box-shadow: 0 10px 20px rgba(0, 0, 0, 0.15);
    }
    
    .card-header {
      background: var(--primary);
      color: white;
      padding: 15px 20px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    
    .card-body {
      padding: 20px;
    }
    
    .form-group {
      margin-bottom: 15px;
    }
    
    label {
      display: block;
      margin-bottom: 5px;
      font-weight: 600;
      color: var(--dark);
    }
    
    select, input {
      width: 100%;
      padding: 12px;
      border: 1px solid #ddd;
      border-radius: 6px;
      font-size: 16px;
    }
    
    .btn {
      display: inline-block;
      background: var(--primary);
      color: white;
      padding: 12px 20px;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 16px;
      font-weight: 600;
      transition: var(--transition);
      text-align: center;
      width: 100%;
    }
    
    .btn:hover {
      background: #2980b9;
    }
    
    .btn-accent {
      background: var(--accent);
    }
    
    .btn-accent:hover {
      background: #c0392b;
    }
    
    .quiz-area {
      background: white;
      border-radius: 12px;
      padding: 25px;
      box-shadow: var(--shadow);
      margin-top: 30px;
      display: none;
    }
    
    .quiz-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 15px;
      border-bottom: 2px solid #eee;
    }
    
    .question {
      margin-bottom: 25px;
      padding: 15px;
      border-radius: 8px;
      background: #f8f9fa;
      border-left: 4px solid var(--primary);
    }
    
    .options {
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
      margin-top: 15px;
    }
    
    .option-btn {
      padding: 12px 15px;
      background: white;
      border: 2px solid #ddd;
      border-radius: 8px;
      text-align: left;
      cursor: pointer;
      transition: var(--transition);
      display: flex;
      align-items: center;
    }
    
    .option-btn:hover {
      border-color: var(--primary);
      background: #e8f4fc;
    }
    
    .option-letter {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      width: 28px;
      height: 28px;
      background: #6c757d;
      color: white;
      border-radius: 50%;
      margin-right: 12px;
      font-weight: bold;
      flex-shrink: 0;
    }
    
    .option-btn.selected {
      border-color: var(--primary);
      background: #e8f4fc;
    }
    
    .option-btn.selected .option-letter {
      background: var(--primary);
    }
    
    .option-btn.correct {
      border-color: var(--success);
      background: #d4edda;
    }
    
    .option-btn.correct .option-letter {
      background: var(--success);
    }
    
    .option-btn.incorrect {
      border-color: var(--danger);
      background: #f8d7da;
    }
    
    .option-btn.incorrect .option-letter {
      background: var(--danger);
    }
    
    .score-display {
      text-align: center;
      margin-top: 20px;
      padding: 15px;
      background: #f8f9fa;
      border-radius: 8px;
      font-weight: bold;
      font-size: 1.2rem;
    }
    
    .progress-bar {
      height: 8px;
      background: #eee;
      border-radius: 4px;
      overflow: hidden;
      margin: 20px 0;
    }
    
    .progress {
      height: 100%;
      background: var(--primary);
      width: 0%;
      transition: width 0.5s ease;
    }
    
    .timer {
      font-size: 1.2rem;
      font-weight: bold;
      color: var(--dark);
      background: #fff4e5;
      padding: 8px 15px;
      border-radius: 20px;
      display: inline-block;
    }
    
    .timer.warning {
      color: var(--warning);
      background: #fff0e5;
    }
    
    .timer.danger {
      color: var(--danger);
      background: #ffece5;
      animation: pulse 1s infinite;
    }
    
    @keyframes pulse {
      0% { opacity: 1; }
      50% { opacity: 0.6; }
      100% { opacity: 1; }
    }
    
    .notification {
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 15px 20px;
      border-radius: 8px;
      color: white;
      background: var(--success);
      box-shadow: var(--shadow);
      transform: translateX(150%);
      transition: transform 0.3s ease;
      z-index: 1000;
    }
    
    .notification.show {
      transform: translateX(0);
    }
    
    .notification.error {
      background: var(--danger);
    }
    
    .loading {
      display: none;
      text-align: center;
      padding: 20px;
    }
    
    .spinner {
      border: 4px solid rgba(0, 0, 0, 0.1);
      border-left-color: var(--primary);
      border-radius: 50%;
      width: 40px;
      height: 40px;
      animation: spin 1s linear infinite;
      margin: 0 auto 15px;
    }
    
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    
    .access-denied {
      text-align: center;
      padding: 40px 20px;
      background: white;
      border-radius: 12px;
      box-shadow: var(--shadow);
      margin: 50px auto;
      max-width: 500px;
    }
    
    .access-denied i {
      font-size: 4rem;
      color: var(--danger);
      margin-bottom: 20px;
    }
    
    .access-denied h2 {
      color: var(--danger);
      margin-bottom: 15px;
    }
    
    .access-denied p {
      margin-bottom: 20px;
      color: var(--dark);
    }
    
    .admin-contact {
      background: #f8f9fa;
      padding: 15px;
      border-radius: 8px;
      margin-top: 20px;
    }
    
    .quiz-feedback {
      margin-top: 15px;
      padding: 15px;
      border-radius: 8px;
      display: none;
    }
    
    .feedback-correct {
      background: #d4edda;
      border-left: 4px solid var(--success);
    }
    
    .feedback-incorrect {
      background: #f8d7da;
      border-left: 4px solid var(--danger);
    }
    
    @media (max-width: 768px) {
      .card-container {
        grid-template-columns: 1fr;
      }
      
      .header-content {
        flex-direction: column;
        text-align: center;
        gap: 10px;
      }
      
      .user-info {
        text-align: center;
      }
      
      .access-denied {
        margin: 20px;
        padding: 20px 15px;
      }
      
      .access-denied i {
        font-size: 3rem;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div class="logo">
        <i class="fas fa-graduation-cap"></i>
        <h1>NYSC Exam Prep</h1>
      </div>
      <div class="user-info">
        <p>Welcome, <span id="userEmail">{{ email }}</span></p>
        <p>Grade Level: <span id="userGrade">{{ grade }}</span></p>
        <button class="logout-btn" onclick="location.href='/logout'">Logout <i class="fas fa-sign-out-alt"></i></button>
      </div>
    </div>
  </header>

  <div class="container">
    <h2 class="dashboard-title">Exam Preparation Dashboard</h2>
    
    <!-- Access denied message (initially hidden) -->
    <div id="accessDenied" class="access-denied" style="display: none;">
      <i class="fas fa-ban"></i>
      <h2>Access Restricted</h2>
      <p>Your account is not authorized to access this system.</p>
      <p>Please contact the administrator to request access.</p>
      <div class="admin-contact">
        <p><strong>Admin Contact:</strong> admin@nyscexamprep.com</p>
      </div>
      <button class="btn" onclick="location.href='/logout'">
        <i class="fas fa-sign-out-alt"></i> Return to Login
      </button>
    </div>
    
    <!-- Main content (initially shown) -->
    <div id="mainContent">
      <div class="card-container">
        <!-- Preset Quiz Card -->
        <div class="card">
          <div class="card-header">
            <i class="fas fa-bolt"></i>
            <h3>Free Trial Quiz</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <label for="subject">Select Subject:</label>
              <select id="subject">
                <option value="public-service-rules">Public Service Rules</option>
                <option value="nysc">NYSC Operations</option>
                <option value="current-affairs">Current Affairs</option>
              </select>
            </div>
            <button class="btn" onclick="generatePresetQuiz()">
              <i class="fas fa-play-circle"></i> Start Preset Quiz
            </button>
          </div>
        </div>

        <!-- Document-based Quiz Card -->
        <div class="card">
          <div class="card-header">
            <i class="fas fa-file-upload"></i>
            <h3>Generate From Document</h3>
          </div>
          <div class="card-body">
            <form id="docForm">
              <div class="form-group">
                <label>Main File (docx/pdf):</label>
                <input type="file" name="file" required>
              </div>
              <div class="form-group">
                <label>Past Questions (optional):</label>
                <input type="file" name="past_file">
              </div>
              <div class="form-group">
                <label>Grade Level:</label>
                <input type="text" name="gl" value="{{ grade }}">
              </div>
              <div class="form-group">
                <label>Subject:</label>
                <select name="subject">
                  <option value="public-service-rules">Public Service Rules</option>
                  <option value="nysc">NYSC Operations</option>
                  <option value="current-affairs">Current Affairs</option>
                </select>
              </div>
              <button type="submit" class="btn btn-accent">
                <i class="fas fa-cogs"></i> Generate Document Quiz
              </button>
            </form>
          </div>
        </div>

        <!-- Progress Card -->
        <div class="card">
          <div class="card-header">
            <i class="fas fa-chart-line"></i>
            <h3>Your Progress</h3>
          </div>
          <div class="card-body">
            <div id="progressStats">
              <p>Quizzes Completed: <span id="quizCount">0</span></p>
              <p>Average Score: <span id="averageScore">0%</span></p>
              <div class="progress-bar">
                <div class="progress" id="overallProgress" style="width: 30%"></div>
              </div>
              <p>Recommended: <span id="recommendedTopic">Public Service Rules</span></p>
            </div>
            <button class="btn" style="margin-top: 15px;">
              <i class="fas fa-history"></i> View History
            </button>
          </div>
        </div>
      </div>

      <!-- Loading Indicator -->
      <div class="loading" id="loadingIndicator">
        <div class="spinner"></div>
        <p>Generating your quiz, please wait...</p>
      </div>

      <!-- Quiz Output -->
      <div id="quizArea" class="quiz-area">
        <div class="quiz-header">
          <h2 id="quizTitle">Generated Quiz</h2>
          <div class="timer" id="quizTimer">20:00</div>
        </div>
        
        <div class="progress-bar">
          <div class="progress" id="quizProgress" style="width: 0%"></div>
        </div>
        
        <div id="quizContent"></div>
        
        <div class="score-display" id="scoreDisplay" style="display: none;">
          Your Score: <span id="scoreValue">0</span>/<span id="totalQuestions">0</span>
        </div>
        
        <div style="text-align: center; margin-top: 20px;">
          <button class="btn" id="submitQuiz" style="display: none;">
            <i class="fas fa-paper-plane"></i> Submit Quiz
          </button>
          <button class="btn" onclick="location.reload()">
            <i class="fas fa-redo"></i> Start New Quiz
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Notification -->
  <div class="notification" id="notification">
    Operation completed successfully!
  </div>

  <script>
    let currentQuiz = null;
    let userAnswers = [];
    let timerInterval = null;
    let timeLeft = 20 * 60; // 20 minutes in seconds
    
    // DOM elements
    const loadingIndicator = document.getElementById('loadingIndicator');
    const quizArea = document.getElementById('quizArea');
    const quizContent = document.getElementById('quizContent');
    const scoreDisplay = document.getElementById('scoreDisplay');
    const scoreValue = document.getElementById('scoreValue');
    const totalQuestions = document.getElementById('totalQuestions');
    const submitQuizBtn = document.getElementById('submitQuiz');
    const quizProgress = document.getElementById('quizProgress');
    const quizTimer = document.getElementById('quizTimer');
    const notification = document.getElementById('notification');
    const mainContent = document.getElementById('mainContent');
    const accessDenied = document.getElementById('accessDenied');
    
    // Check if user is whitelisted
    function checkWhitelistStatus() {
      const userEmail = "{{ email }}".toLowerCase();
      const whitelistedEmails = [
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
        "winter19@gmail.com"
      ].map(email => email.toLowerCase());
      
      if (!whitelistedEmails.includes(userEmail)) {
        mainContent.style.display = 'none';
        accessDenied.style.display = 'block';
        showNotification("Your account is not authorized to access this system.", true);
      }
    }
    
    // Show notification function
    function showNotification(message, isError = false) {
      notification.textContent = message;
      notification.className = 'notification' + (isError ? ' error' : '');
      notification.classList.add('show');
      
      setTimeout(() => {
        notification.classList.remove('show');
      }, 3000);
    }
    
    // Format time display
    function formatTime(seconds) {
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    // Start quiz timer
    function startTimer() {
      // Reset timer
      timeLeft = 20 * 60;
      quizTimer.textContent = formatTime(timeLeft);
      quizTimer.classList.remove('warning', 'danger');
      
      // Clear existing interval
      if (timerInterval) clearInterval(timerInterval);
      
      // Start new timer
      timerInterval = setInterval(() => {
        timeLeft--;
        quizTimer.textContent = formatTime(timeLeft);
        
        // Change color when time is running out
        if (timeLeft < 300) { // 5 minutes
          quizTimer.classList.add('warning');
        }
        if (timeLeft < 60) { // 1 minute
          quizTimer.classList.add('danger');
        }
        if (timeLeft <= 0) {
          clearInterval(timerInterval);
          showNotification("Time's up! Submitting your quiz.", true);
          calculateScore();
        }
      }, 1000);
    }
    
    // Update progress bar
    function updateProgressBar() {
      if (!currentQuiz) return;
      
      const answered = userAnswers.filter(a => a !== null).length;
      const progress = (answered / currentQuiz.quiz.length) * 100;
      quizProgress.style.width = `${progress}%`;
    }
    
    // Check session validity
    function checkSessionValidity() {
      axios.get('/check_session')
        .then(response => {
          // Session is valid
        })
        .catch(error => {
          if (error.response && error.response.status === 401) {
            showNotification("Your session has expired. Please log in again.", true);
            setTimeout(() => {
              window.location.href = '/';
            }, 2000);
          }
        });
    }
    
    async function generatePresetQuiz() {
      const subject = document.getElementById("subject").value;
      
      try {
        loadingIndicator.style.display = 'block';
        
        const res = await axios.post("/generate_preset_quiz", {
          subject: subject,
          gl: "{{ grade }}"
        });
        
        loadingIndicator.style.display = 'none';
        renderQuiz(res.data);
        showNotification("Quiz generated successfully!");
      } catch (err) {
        loadingIndicator.style.display = 'none';
        if (err.response && err.response.status === 403) {
          showNotification("Access denied. Contact admin.", true);
        } else {
          showNotification("Error generating quiz: " + (err.response?.data?.error || err.message), true);
        }
      }
    }

    document.getElementById("docForm").onsubmit = async (e) => {
      e.preventDefault();
      const formData = new FormData(e.target);
      
      try {
        loadingIndicator.style.display = 'block';
        
        const res = await axios.post("/generate", formData, {
          headers: { "Content-Type": "multipart/form-data" }
        });
        
        loadingIndicator.style.display = 'none';
        renderQuiz(res.data);
        showNotification("Quiz generated successfully!");
      } catch (err) {
        loadingIndicator.style.display = 'none';
        if (err.response && err.response.status === 403) {
          showNotification("Access denied. Contact admin.", true);
        } else {
          showNotification("Error generating quiz: " + (err.response?.data?.error || err.message), true);
        }
      }
    };

    function renderQuiz(data) {
      currentQuiz = data;
      userAnswers = new Array(data.quiz.length).fill(null);
      
      quizArea.style.display = "block";
      document.getElementById("quizTitle").innerText = "Generated Quiz";
      quizContent.innerHTML = "";
      scoreDisplay.style.display = "none";
      submitQuizBtn.style.display = "block";
      
      // Scroll to quiz area
      quizArea.scrollIntoView({ behavior: 'smooth' });
      
      // Render quiz questions
      data.quiz.forEach((q, i) => {
        const div = document.createElement("div");
        div.className = "question";
        div.innerHTML = `<b>Q${i+1}:</b> ${q.question}`;
        
        const optionsDiv = document.createElement("div");
        optionsDiv.className = "options";
        
        // Ensure we have exactly 4 options
        const options = [...q.options];
        while (options.length < 4) {
          options.push(`Option ${String.fromCharCode(65 + options.length)}`);
        }
        
        options.forEach((opt, optIndex) => {
          const btn = document.createElement("button");
          btn.className = "option-btn";
          btn.innerHTML = `
            <span class="option-letter">${String.fromCharCode(65 + optIndex)}</span>
            <span class="option-text">${opt}</span>
          `;
          btn.onclick = () => {
            // Remove selected class from all options in this question
            optionsDiv.querySelectorAll('.option-btn').forEach(b => {
              b.classList.remove('selected');
            });
            
            // Highlight selected option
            btn.classList.add('selected');
            
            // Store answer
            userAnswers[i] = optIndex;
            updateProgressBar();
          };
          optionsDiv.appendChild(btn);
        });
        
        div.appendChild(optionsDiv);
        quizContent.appendChild(div);
      });
      
      // Add event listener to submit button
      submitQuizBtn.onclick = calculateScore;
      
      // Initialize progress bar
      updateProgressBar();
      
      // Start the timer
      startTimer();
      
      // Update total questions count
      totalQuestions.textContent = data.quiz.length;
    }
    
    function calculateScore() {
      if (!currentQuiz) return;
      
      // Stop the timer
      if (timerInterval) clearInterval(timerInterval);
      
      let score = 0;
      
      // Check answers and provide feedback
      currentQuiz.quiz.forEach((q, i) => {
        const questionDiv = quizContent.children[i];
        const optionsDiv = questionDiv.querySelector('.options');
        const userAnswerIndex = userAnswers[i];
        const options = optionsDiv.querySelectorAll('.option-btn');
        
        // Find the correct answer index
        let correctIndex = -1;
        options.forEach((btn, idx) => {
          const optionText = btn.querySelector('.option-text').textContent;
          if (optionText === q.correct) {
            correctIndex = idx;
          }
        });
        
        // Mark correct answer
        if (correctIndex >= 0) {
          options[correctIndex].classList.add('correct');
        }
        
        // Mark incorrect user answer if wrong
        if (userAnswerIndex !== null && userAnswerIndex !== correctIndex) {
          options[userAnswerIndex].classList.add('incorrect');
        }
        
        // Update score if correct
        if (userAnswerIndex === correctIndex) {
          score++;
        }
      });
      
      // Display score
      scoreValue.textContent = score;
      scoreDisplay.style.display = "block";
      submitQuizBtn.style.display = "none";
      
      // Show notification with score
      showNotification(`Quiz completed! Your score: ${score}/${currentQuiz.quiz.length}`);
    }
    
    // Initialize some demo progress data
    document.addEventListener('DOMContentLoaded', function() {
      document.getElementById('quizCount').textContent = '3';
      document.getElementById('averageScore').textContent = '75%';
      document.getElementById('overallProgress').style.width = '60%';
      
      // Check if user is whitelisted
      checkWhitelistStatus();
      
      // Check session validity periodically
      setInterval(checkSessionValidity, 60000); // Check every minute
    });
  </script>
</body>
</html>