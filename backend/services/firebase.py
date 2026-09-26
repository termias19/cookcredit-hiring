"""
Firebase Admin SDK — Auth, Storage, and the read-only Skill handoff record.

Firestore has been replaced by PostgreSQL. This module retains:
  - Firebase Auth (token verification in middleware/auth.py)
  - Firebase Storage (profile images and assessment recordings)
  - Firestore read of a finalized CookCredit Skill record during handoff
"""

import firebase_admin
from firebase_admin import credentials, auth, storage as admin_storage, firestore
import os
import json

STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "foodnlit-1123e.firebasestorage.app")

_auth = None


def init_firebase():
    """Initialize Firebase Admin SDK — called once at startup."""
    global _auth

    if firebase_admin._apps:
        _auth = auth
        return

    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            sa_dict = json.loads(sa_json)
            cred = credentials.Certificate(sa_dict)
        except json.JSONDecodeError as e:
            raise ValueError(f"FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}")
    elif os.getenv('FIREBASE_USE_ADC') == '1':
        cred = credentials.ApplicationDefault()
    else:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "./serviceAccountKey.json")
        if not os.path.exists(cred_path):
            raise FileNotFoundError(
                f"\n\n❌  Firebase credentials not found at: {cred_path}\n"
                f"    1. Go to Firebase Console → Project Settings → Service Accounts\n"
                f"    2. Click 'Generate new private key'\n"
                f"    3. Save the JSON file as 'serviceAccountKey.json' inside backend/\n"
            )
        cred = credentials.Certificate(cred_path)

    options = {'projectId': os.environ['FIREBASE_PROJECT_ID']} if os.getenv('FIREBASE_PROJECT_ID') else None
    firebase_admin.initialize_app(cred, options)
    _auth = auth
    print("✅  Firebase Auth connected (Firestore replaced by PostgreSQL)")


def get_auth():
    global _auth
    if _auth is None:
        init_firebase()
    return _auth


def get_storage_bucket():
    if not firebase_admin._apps:
        init_firebase()
    return admin_storage.bucket(STORAGE_BUCKET)


def get_firestore_client():
    if not firebase_admin._apps:
        init_firebase()
    return firestore.client()
