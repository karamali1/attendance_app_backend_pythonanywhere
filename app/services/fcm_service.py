import os

import firebase_admin
from firebase_admin import credentials, messaging


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SERVICE_ACCOUNT_PATH = os.path.join(BASE_DIR, "firebase_service_account.json")


def initialize_firebase_admin():
    if firebase_admin._apps:
        return

    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)


def send_push_notification_to_token(
    fcm_token: str,
    title: str,
    body: str,
    data: dict | None = None
):
    initialize_firebase_admin()

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data or {},
        token=fcm_token,
    )

    return messaging.send(message)