import { auth, signInWithEmailAndPassword, createUserWithEmailAndPassword, onAuthStateChanged } from "./firebase.js";

document.addEventListener("DOMContentLoaded", () => {
    // auth buttons - check for existence before adding listeners
    const loginBtn = document.getElementById("loginBtn");
    const signupBtn = document.getElementById("signupBtn");
    const authMessage = document.getElementById("authMessage");

    if (loginBtn) {
        loginBtn.addEventListener("click", async () => {
            const email = document.getElementById("email").value;
            const pass = document.getElementById("password").value;
            try {
                await signInWithEmailAndPassword(auth, email, pass);
                if (authMessage) authMessage.textContent = "Login successful!";
                window.location.href = '/dashboard';
            } catch (err) {
                if (authMessage) authMessage.textContent = "Login failed: " + err.message;
            }
        });
    }

    if (signupBtn) {
        signupBtn.addEventListener("click", async () => {
            const email = document.getElementById("email").value;
            const pass = document.getElementById("password").value;
            try {
                await createUserWithEmailAndPassword(auth, email, pass);
                if (authMessage) authMessage.textContent = "Account created - signed in.";
                window.location.href = '/dashboard';
            } catch (err) {
                if (authMessage) authMessage.textContent = "Signup failed: " + err.message;
            }
        });
    }

    // Check auth state on page load. If already logged in, redirect to dashboard.
    onAuthStateChanged(auth, user => {
        if (user) {
            window.location.href = '/dashboard';
        }
    });
});
