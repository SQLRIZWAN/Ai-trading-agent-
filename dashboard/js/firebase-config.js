/**
 * firebase-config.js
 *
 * SETUP: Replace the values below with your own Firebase project config.
 * Get them from: Firebase Console → Project Settings → Your Apps → Web App → SDK setup
 *
 * Until you configure Firebase, the dashboard runs in DEMO PREVIEW mode
 * with mock data so you can see the full UI immediately.
 */

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore.js";
import { getAuth, GoogleAuthProvider } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

// ── Replace with your Firebase project config ──────────────────────────────
const firebaseConfig = {
  apiKey:            "YOUR_API_KEY",
  authDomain:        "YOUR_PROJECT.firebaseapp.com",
  projectId:         "YOUR_PROJECT_ID",
  storageBucket:     "YOUR_PROJECT.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId:             "YOUR_APP_ID"
};

const IS_CONFIGURED = firebaseConfig.apiKey !== "YOUR_API_KEY";

let app, db, auth, googleProvider;

if (IS_CONFIGURED) {
  app           = initializeApp(firebaseConfig);
  db            = getFirestore(app);
  auth          = getAuth(app);
  googleProvider = new GoogleAuthProvider();
} else {
  // ── Demo/Preview mode: provide stub objects so the UI still works ────────
  console.info(
    "%c AI Trading Agent — Preview Mode %c\n" +
    "Firebase not configured yet. " +
    "Update dashboard/js/firebase-config.js with your project config.\n" +
    "See README.md for full setup instructions.",
    "background:#4d9fff;color:#fff;font-weight:bold;padding:2px 6px;border-radius:4px;",
    ""
  );

  // Stub Firestore that returns empty data
  const noop = () => Promise.resolve();
  const stubDoc  = { exists: () => false, data: () => null };
  const stubSnap = { docs: [] };

  db = {
    collection: () => ({
      doc:     () => ({ get: () => Promise.resolve(stubDoc), onSnapshot: (cb) => { cb({ exists: () => false, data: () => ({}) }); return () => {}; } }),
      add:     () => Promise.resolve({ id: "demo_id" }),
      limit:   () => ({ stream: () => [] }),
      get:     () => Promise.resolve(stubSnap),
    }),
  };

  auth = {
    currentUser: null,
    onAuthStateChanged: (cb) => { cb(null); return () => {}; },
  };

  googleProvider = {};
}

export { db, auth, googleProvider };
