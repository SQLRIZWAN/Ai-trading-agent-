"""
firebase_client.py — Firestore read/write helper.
Initialises Firebase Admin SDK once and exposes a 'db' client.
"""

import json
import os

import firebase_admin
from firebase_admin import credentials, firestore

from scripts.utils.config import Config
from scripts.utils.logger import get_logger

logger = get_logger("firebase_client")

_app = None
db = None


def init_firebase():
    """Initialise Firebase app (idempotent)."""
    global _app, db

    if _app is not None:
        return db

    # Build service-account dict from individual env vars (GitHub Secrets)
    service_account = {
        "type": "service_account",
        "project_id": Config.FIREBASE_PROJECT_ID,
        "private_key": Config.FIREBASE_PRIVATE_KEY,
        "client_email": Config.FIREBASE_CLIENT_EMAIL,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    # Alternatively accept a full JSON blob in FIREBASE_SERVICE_ACCOUNT
    raw_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "")
    if raw_json:
        try:
            service_account = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("FIREBASE_SERVICE_ACCOUNT is not valid JSON; falling back to individual vars")

    cred = credentials.Certificate(service_account)
    _app = firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase initialised for project: %s", Config.FIREBASE_PROJECT_ID)
    return db


# Auto-init on import
try:
    db = init_firebase()
except Exception as exc:
    logger.error("Firebase init failed: %s", exc)
    db = None


# ─── Convenience helpers ────────────────────────────────────────────────────

def set_doc(collection: str, doc_id: str, data: dict, merge: bool = True):
    """Write (or merge) a document."""
    db.collection(collection).document(doc_id).set(data, merge=merge)


def get_doc(collection: str, doc_id: str) -> dict | None:
    """Read a document; returns None if missing."""
    snap = db.collection(collection).document(doc_id).get()
    return snap.to_dict() if snap.exists else None


def add_doc(collection: str, data: dict) -> str:
    """Add a document with auto-generated ID; returns the new doc ID."""
    ref = db.collection(collection).add(data)
    return ref[1].id


def get_collection(collection: str, limit: int = 100) -> list[dict]:
    """Fetch up to `limit` documents from a collection."""
    docs = db.collection(collection).limit(limit).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def update_doc(collection: str, doc_id: str, data: dict):
    """Update specific fields in a document."""
    db.collection(collection).document(doc_id).update(data)
