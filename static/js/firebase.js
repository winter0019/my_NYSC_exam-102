// static/js/firebase.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
import { getFirestore, collection, addDoc, query, getDocs, orderBy, limit } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";

// --- Replace with your Firebase config ---
const firebaseConfig = {
  apiKey: "AIzaSyCyU4fCiZEo_jGCf3Am7_7CGwH43EjqQD4",
  authDomain: "exam-prep-102.firebaseapp.com",
  projectId: "exam-prep-102",
  storageBucket: "exam-prep-102.firebasestorage.app",
  messagingSenderId: "1048082051309",
  appId: "1:1048082051309:web:60c9ef8aaa0e9f638d5ce4",
  measurementId: "G-0ZRVZBM37H"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

export { auth, db, signInWithEmailAndPassword, createUserWithEmailAndPassword, onAuthStateChanged, signOut, collection, addDoc, query, getDocs, orderBy, limit };
