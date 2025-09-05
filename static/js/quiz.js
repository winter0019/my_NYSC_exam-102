const generateBtn = document.getElementById("generateBtn");
const attachmentInput = document.getElementById("attachmentInput");
const practiceGrade = document.getElementById("practiceGrade");
const loadingIndicator = document.getElementById("loadingIndicator");
const quizBox = document.getElementById("quizBox");
const discussionBox = document.getElementById("discussionBox");
const quizContainer = document.getElementById("quizContainer");
const discussionContainer = document.getElementById("discussionContainer");
const quizForm = document.getElementById("quizForm"); // Add an ID to your form if it doesn't have one
const quizScoreContainer = document.getElementById("quizScoreContainer"); // Add this to your HTML
const scoreSpan = document.getElementById("score");
const totalSpan = document.getElementById("total");

let currentQuizData = null;

// --- Render Functions ---
function renderQuizQuestions(questions) {
    quizContainer.innerHTML = "";
    const optionLetters = ["A", "B", "C", "D"];
    questions.forEach((q, idx) => {
        const div = document.createElement("div");
        div.className = "bg-gray-50 p-4 rounded shadow mb-4";
        const optionsHtml = q.options.map((opt, i) => `
            <label class="flex items-center space-x-2 cursor-pointer mb-1">
                <input type="radio" name="quiz-q${idx}" value="${opt}" class="form-radio h-4 w-4 text-blue-600">
                <span class="font-semibold">${optionLetters[i]}.</span>
                <span>${opt}</span>
            </label>
        `).join("");
        div.innerHTML = `
            <p class="mb-2 font-medium"><strong>Q${idx + 1} [${q.category}]</strong>: ${q.question}</p>
            <div class="options">${optionsHtml}</div>
            <p id="feedback-q${idx}" class="mt-2 hidden"></p>
        `;
        quizContainer.appendChild(div);
    });
}

function renderDiscussionQuestions(discussions) {
    discussionContainer.innerHTML = "";
    discussions.forEach((d, idx) => {
        const div = document.createElement("div");
        div.className = "bg-gray-50 p-3 rounded shadow mb-2";
        div.innerHTML = `<p class="font-medium">D${idx + 1}: ${d.q}</p>`;
        discussionContainer.appendChild(div);
    });
}

function displayScore(score, total) {
    scoreSpan.textContent = score;
    totalSpan.textContent = total;
    quizScoreContainer.classList.remove("hidden");
}

// --- Event Listeners ---
generateBtn.addEventListener("click", async () => {
    if (!attachmentInput.files.length) {
        alert("Please select a file to upload.");
        return;
    }

    const file = attachmentInput.files[0];
    const formData = new FormData();
    formData.append("document", file); // Corrected to 'document' to match backend
    formData.append("grade", practiceGrade.value);

    loadingIndicator.classList.remove("hidden");
    quizContainer.innerHTML = "";
    discussionContainer.innerHTML = "";
    quizBox.classList.add("hidden");
    discussionBox.classList.add("hidden");
    quizScoreContainer.classList.add("hidden");

    try {
        const res = await fetch("/api/quiz/upload", { // Corrected endpoint to match backend
            method: "POST",
            body: formData
        });

        if (!res.ok) {
            const errData = await res.json();
            alert(errData.error || "Failed to generate questions.");
            return;
        }

        const data = await res.json();
        currentQuizData = data.questions;

        if (currentQuizData && currentQuizData.length > 0) {
            quizBox.classList.remove("hidden");
            renderQuizQuestions(currentQuizData);
        }

        if (data.discussions && data.discussions.length > 0) {
            discussionBox.classList.remove("hidden");
            renderDiscussionQuestions(data.discussions);
        }

    } catch (err) {
        console.error(err);
        alert("An error occurred while generating questions.");
    } finally {
        loadingIndicator.classList.add("hidden");
    }
});

// Assuming your HTML has a form with id="quizForm" and a button with id="submitQuizBtn"
quizForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!currentQuizData) {
        alert("Please generate a quiz first.");
        return;
    }

    let score = 0;
    currentQuizData.forEach((q, idx) => {
        const selected = document.querySelector(`input[name="quiz-q${idx}"]:checked`);
        const feedbackEl = document.getElementById(`feedback-q${idx}`);
        const questionDiv = document.querySelector(`[name="quiz-q${idx}"]`).closest('div');

        // Disable all radio buttons
        questionDiv.querySelectorAll('input[type="radio"]').forEach(radio => radio.disabled = true);

        // Check the answer and apply styles
        if (selected && selected.value === q.answer) {
            score++;
            selected.parentElement.classList.add("bg-green-200");
            feedbackEl.textContent = "Correct!";
            feedbackEl.className = "mt-2 text-green-600";
        } else {
            if (selected) {
                selected.parentElement.classList.add("bg-red-200");
            }
            // Highlight the correct answer
            const correctOptionEl = questionDiv.querySelector(`input[value="${q.answer}"]`);
            if (correctOptionEl) {
                correctOptionEl.parentElement.classList.add("bg-green-200");
            }
            feedbackEl.textContent = `Incorrect. The correct answer was "${q.answer}".`;
            feedbackEl.className = "mt-2 text-red-600";
        }
        feedbackEl.classList.remove("hidden");
    });
    displayScore(score, currentQuizData.length);
});
