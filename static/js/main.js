const generateBtn = document.getElementById("generateBtn");
const attachmentInput = document.getElementById("attachmentInput");
const loadingIndicator = document.getElementById("loadingIndicator");
const discussionsContainer = document.getElementById("discussionsContainer");
const logoutBtn = document.getElementById("logoutBtn");

logoutBtn.addEventListener("click", async () => {
  window.location.href = "/logout";
});

generateBtn.addEventListener("click", async () => {
  const file = attachmentInput.files[0];
  if (!file) return alert("Select a file first");

  loadingIndicator.classList.remove("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/generate", { method: "POST", body: formData });
    const data = await res.json();
    loadingIndicator.classList.add("hidden");

    if (res.ok) {
      console.log("Quiz & Discussions:", data);
      discussionsContainer.innerHTML = "";
      data.discussions.forEach(d => {
        const div = document.createElement("div");
        div.textContent = d.q;
        discussionsContainer.appendChild(div);
      });
    } else {
      alert(data.error || "Failed to generate questions");
    }
  } catch (err) {
    loadingIndicator.classList.add("hidden");
    alert("Error connecting to server");
  }
});
