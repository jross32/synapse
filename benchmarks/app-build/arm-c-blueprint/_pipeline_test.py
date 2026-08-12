import inspect

import passwords as m

_want_0 = ['password']
assert hasattr(m, 'hash_password'), (
    'passwords.hash_password' + ' is missing. The contract requires: '
    + 'hash_password(password)' + '. Defined here: ' + str([n for n in dir(m) if not n.startswith('_')]))
_got_0 = list(inspect.signature(m.hash_password).parameters)[:1]
assert _got_0 == _want_0, (
    'passwords.hash_password' + ' takes ' + str(_got_0)
    + ' but the contract requires ' + str(_want_0)
    + '. Callers were written against the contract, so rename the parameters to match exactly - including their order.')
_want_1 = ['password', 'stored']
assert hasattr(m, 'verify_password'), (
    'passwords.verify_password' + ' is missing. The contract requires: '
    + 'verify_password(password, stored)' + '. Defined here: ' + str([n for n in dir(m) if not n.startswith('_')]))
_got_1 = list(inspect.signature(m.verify_password).parameters)[:2]
assert _got_1 == _want_1, (
    'passwords.verify_password' + ' takes ' + str(_got_1)
    + ' but the contract requires ' + str(_want_1)
    + '. Callers were written against the contract, so rename the parameters to match exactly - including their order.')

from passwords import *
import secrets

def test_hash_password():
    password = "testpassword123"
    hashed = hash_password(password)
    assert isinstance(hashed, str)
    parts = hashed.split('$')
    assert len(parts) == 4
    algorithm, iterations, salt_hex, digest_hex = parts
    assert algorithm == 'pbkdf2_hmac'
    assert int(iterations) == 200000
    assert len(salt_hex) == 32
    assert len(digest_hex) == 64

def test_verify_password():
    password = "testpassword123"
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)
    assert not verify_password(None, hashed)
    assert not verify_password("", hashed)
    assert not verify_password("testpassword123", None)
    assert not verify_password("testpassword123", "")
    print('OK')