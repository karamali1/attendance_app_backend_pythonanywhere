import firebase_admin
from firebase_admin import credentials, auth


if not firebase_admin._apps:
    cred = credentials.Certificate(
    "/home/KaramAli111/backend_copy_pythonanywhere/firebase_service_account.json"
)
    firebase_admin.initialize_app(cred)


def verify_firebase_token(firebase_token: str):
    decoded_token = auth.verify_id_token(firebase_token)

    email = decoded_token.get("email")
    uid = decoded_token.get("uid")
    email_verified = decoded_token.get("email_verified", False)

    if not email:
        raise ValueError("Firebase token does not contain an email")

    if not email_verified:
        raise ValueError("Email is not verified")

    return {
        "uid": uid,
        "email": email,
        "email_verified": email_verified,
    }


def verify_firebase_token_for_registration(firebase_token: str):
    decoded_token = auth.verify_id_token(firebase_token)

    email = decoded_token.get("email")
    uid = decoded_token.get("uid")
    email_verified = decoded_token.get("email_verified", False)

    if not email:
        raise ValueError("Firebase token does not contain an email")

    return {
        "uid": uid,
        "email": email,
        "email_verified": email_verified,
    }