from storage import *
import secrets

def test_passwords():
    password = "testpassword123"
    hashed = hash_password(password)
    assert isinstance(hashed, str)
    
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)

print('OK')