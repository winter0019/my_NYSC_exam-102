import { auth, db, onAuthStateChanged, collection, addDoc, query, onSnapshot, orderBy } from "./firebase.js";

const discussionTitle = document.getElementById("discussion-title");
const commentsList = document.getElementById("comments-list");
const commentInput = document.getElementById("comment-input");
const submitCommentBtn = document.getElementById("submit-comment");
const authMessageBox = document.getElementById("auth-message-box");
const discussionContent = document.getElementById("discussion-content");

let currentUser = null;

// The discussion_q_id is set in the discussion.html template
const q_id = typeof discussion_q_id !== 'undefined' ? discussion_q_id : null;

// Firestore appId placeholder
const appId = "default-app-id";

// Submit new comment
submitCommentBtn?.addEventListener("click", async () => {
    if (!currentUser) return alert("Please log in to comment.");
    
    const commentText = commentInput.value.trim();
    if (!commentText) return alert("Comment cannot be empty.");

    try {
        const commentsCollection = collection(db, `artifacts/${appId}/public/data/discussions/${q_id}/comments`);
        await addDoc(commentsCollection, {
            userId: currentUser.uid,
            name: currentUser.email.split('@')[0],
            comment: commentText,
            timestamp: new Date().toISOString()
        });

        commentInput.value = "";
    } catch (err) {
        console.error("Error adding comment:", err);
        alert("Failed to submit comment. Please try again.");
    }
});

// Listen for auth state changes
onAuthStateChanged(auth, (user) => {
    currentUser = user;

    if (user) {
        authMessageBox?.classList.add("hidden");
        discussionContent?.classList.remove("hidden");
    } else {
        authMessageBox?.classList.remove("hidden");
        discussionContent?.classList.add("hidden");
    }
});

// Real-time listener for comments
if (q_id) {
    const commentsCollection = collection(db, `artifacts/${appId}/public/data/discussions/${q_id}/comments`);
    const q = query(commentsCollection, orderBy("timestamp", "asc"));

    onSnapshot(q, (snapshot) => {
        if (!commentsList) return;

        commentsList.innerHTML = '';
        snapshot.forEach((doc) => {
            const commentData = doc.data();
            const commentDiv = document.createElement("div");
            commentDiv.className = "p-3 mb-2 border rounded bg-gray-50 shadow-sm";

            commentDiv.innerHTML = `
                <div class="flex justify-between text-sm text-gray-600 mb-1">
                    <span class="font-semibold">${escapeHTML(commentData.name)}</span>
                    <span>${new Date(commentData.timestamp).toLocaleString()}</span>
                </div>
                <div class="text-gray-800">${escapeHTML(commentData.comment)}</div>
            `;
            commentsList.appendChild(commentDiv);
        });
    });
}

// Escape HTML to prevent XSS
function escapeHTML(str) {
    return String(str)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
