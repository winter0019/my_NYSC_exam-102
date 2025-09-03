// static/js/login.js
const loginBtn = document.getElementById("loginBtn");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const loginMessage = document.getElementById("loginMessage");

loginBtn.addEventListener("click", async (e) => {
  e.preventDefault(); // prevent form reload

  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value.trim();

  if (!email || !password) {
    loginMessage.textContent = "Email and password required";
    loginMessage.classList.remove("hidden");
    return;
  }

  try {
    const res = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    // If Flask returns HTML (render_template), handle it
    const contentType = res.headers.get("content-type");

    if (contentType && contentType.includes("application/json")) {
      const data = await res.json();
      if (res.ok && data.ok) {
        window.location.href = "/dashboard";
      } else {
        loginMessage.textContent = data.error || "Login failed";
        loginMessage.classList.remove("hidden");
      }
    } else {
      // Assume HTML response → login success
      if (res.ok) {
        window.location.href = "/dashboard";
      } else {
        loginMessage.textContent = "Invalid credentials";
        loginMessage.classList.remove("hidden");
      }
    }
  } catch (err) {
    console.error("Login request failed:", err);
    loginMessage.textContent = "Error connecting to server";
    loginMessage.classList.remove("hidden");
  }
});
