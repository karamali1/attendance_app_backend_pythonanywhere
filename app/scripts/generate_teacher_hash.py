from app.core.auth import hash_password

plain_password = "teacher123"
hashed_password = hash_password(plain_password)
print(hashed_password)
