import hashlib
import hmac
import os
import secrets
import string

ITERATIONS = 210_000

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False

def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 10:
        return False, "Şifre en az 10 karakter olmalı."
    if not any(c.islower() for c in password):
        return False, "Şifre en az bir küçük harf içermeli."
    if not any(c.isupper() for c in password):
        return False, "Şifre en az bir büyük harf içermeli."
    if not any(c.isdigit() for c in password):
        return False, "Şifre en az bir rakam içermeli."
    return True, ""

def new_token() -> str:
    return secrets.token_urlsafe(32)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def generate_temp_password(length: int = 14) -> str:
    # En az birer büyük/küçük/rakam garanti edilir; kafa karıştıran karakterler azaltılır.
    lowers = "abcdefghjkmnpqrstuvwxyz"
    uppers = "ABCDEFGHJKMNPQRSTUVWXYZ"
    digits = "23456789"
    allchars = lowers + uppers + digits + "!@#"
    chars = [
        secrets.choice(lowers),
        secrets.choice(uppers),
        secrets.choice(digits),
        secrets.choice("!@#"),
    ]
    chars.extend(secrets.choice(allchars) for _ in range(max(0, length - len(chars))))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
