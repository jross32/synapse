from api import *

# Test hash_password and verify_password
password = "test123"
hashed_password = hash_password(password)
assert isinstance(hashed_password, str)
assert verify_password("test123", hashed_password)
assert not verify_password("wrongpassword", hashed_password)

# Test create_user and get_user_by_email
email = "test@example.com"
create_user(email, hashed_password)
user = get_user_by_email(email)
assert user.email == email

# Test add_record and list_records
record_id = add_record(user.id, "Test Record", 100.0, "2023-04-01")
records = list_records(user.id)
assert len(records) == 1
assert records[0].id == record_id
assert records[0].title == "Test Record"
assert records[0].amount == 100.0
assert records[0].date == "2023-04-01"

# Test delete_record
delete_record(record_id, user.id)
records = list_records(user.id)
assert len(records) == 0

# Test create_session and delete_session
token = create_session(user.id)
user_id = storage.user_id_for_token(token)
assert user_id == user.id
delete_session(token)

print('OK')