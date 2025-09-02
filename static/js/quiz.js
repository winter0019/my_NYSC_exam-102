const generateBtn = document.getElementById("generateBtn");
const attachmentInput = document.getElementById("attachmentInput");
const practiceGrade = document.getElementById("practiceGrade");
const loadingIndicator = document.getElementById("loadingIndicator");
const quizBox = document.getElementById("quizBox");
const discussionBox = document.getElementById("discussionBox");
const quizContainer = document.getElementById("quizContainer");
const discussionContainer = document.getElementById("discussionContainer");

generateBtn.addEventListener("click", async () => {
    if (!attachmentInput.files.length) {
        alert("Please select a file to upload.");
        return;
    }

    const file = attachmentInput.files[0];
    const formData = new FormData();
    formData.append("file", file);
    formData.append("gl", practiceGrade.value);

    loadingIndicator.classList.remove("hidden");
    quizContainer.innerHTML = "";
    discussionContainer.innerHTML = "";
    quizBox.classList.add("hidden");
    discussionBox.classList.add("hidden");

    try {
        const res = await fetch("/generate", {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            alert(data.error || "Failed to generate questions.");
            loadingIndicator.classList.add("hidden");
            return;
        }

        // Render quiz questions with radio buttons
        quizBox.classList.remove("hidden");
        const optionLetters = ["A", "B", "C", "D"];
        data.quiz.forEach((q, idx) => {
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
            `;

            quizContainer.appendChild(div);
        });

        // Render discussion questions
        discussionBox.classList.remove("hidden");
        data.discussions.forEach((d, idx) => {
            const div = document.createElement("div");
            div.className = "bg-gray-50 p-3 rounded shadow mb-2";
            div.innerHTML = `<p class="font-medium">D${idx + 1}: ${d.q}</p>`;
            discussionContainer.appendChild(div);
        });

    } catch (err) {
        console.error(err);
        alert("An error occurred while generating questions.");
    } finally {
        loadingIndicator.classList.add("hidden");
    }
});
