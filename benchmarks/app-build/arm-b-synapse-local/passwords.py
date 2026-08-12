import hashlib
import hmac
import secrets

def hash_password(password: str) -> str:
    # Generate a random 16-byte salt
    salt = secrets.token_bytes(16)
    
    # Hash the password using pbkdf2_hmac with SHA-256, 200000 iterations
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000)
    
    # Encode the salt and digest in hex
    salt_hex = salt.hex()
    digest_hex = digest.hex()
    
    # Construct the result string
    result = f"pbkdf2_sha256$200000${salt_hex}${digest_hex}"
    
    return result

def verify_password(password: str, stored: str) -> bool:
    if not stored or '$' not in stored:
        return False
    
    try:
        # Split the stored hash into its components
        algorithm, iteration_count, salt_hex, digest_hex = stored.split('$')
        
        # Check if the algorithm is supported
        if algorithm != 'pbkdf2_sha256':
            return False
        
        # Convert the iteration count to an integer
        iteration_count = int(iteration_count)
        
        # Convert the salt and digest from hex to bytes
        salt = bytes.fromhex(salt_hex)
        stored_digest = bytes.fromhex(digest_hex)
        
        # Recompute the digest using the provided password, salt, and iteration count
        new_digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iteration_count)
        
        # Compare the recomputed digest with the stored digest
        return hmac.compare_digest(new_digest, stored_digest)
    
    except (ValueError, TypeError):
        # Return False if the stored string is malformed or in an unknown format
        return False

# Example usage:
if __name__ == "__main__":
    password = "my_secure_password"
    hashed_password = hash_password(password)
    print("Hashed Password:", hashed_password)

    is_valid = verify_password(password, hashed_password)
    print("Password Valid:", is_valid)