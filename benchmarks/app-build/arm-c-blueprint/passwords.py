import hashlib
import hmac
import secrets

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000)
    return f'pbkdf2_sha256$200000${salt.hex()}${digest.hex()}'

def verify_password(password: str, stored: str) -> bool:
    if not stored or '$' not in stored:
        return False
    parts = stored.split('$')
    if len(parts) != 4:
        return False
    algorithm, iterations, salt_hex, digest_hex = parts
    if algorithm != 'pbkdf2_sha256':
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        stored_digest = bytes.fromhex(digest_hex)
        new_digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, int(iterations))
        return hmac.compare_digest(stored_digest, new_digest)
    except (ValueError, TypeError):
        return False