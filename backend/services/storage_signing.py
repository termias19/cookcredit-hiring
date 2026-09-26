"""Sign short-lived GCS URLs with the Cloud Run identity, without private keys."""
import os
import google.auth
from google.auth.transport.requests import Request


def signed_url(blob, **kwargs):
    if os.environ.get('FIREBASE_USE_ADC') != '1':
        return blob.generate_signed_url(**kwargs)
    email = os.environ.get('STORAGE_SIGNING_SERVICE_ACCOUNT', '')
    if not email.endswith('.iam.gserviceaccount.com'):
        raise RuntimeError('Storage signing identity is not configured')
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not credentials.valid:
        credentials.refresh(Request())
    return blob.generate_signed_url(credentials=credentials, service_account_email=email,
                                    access_token=credentials.token, **kwargs)
