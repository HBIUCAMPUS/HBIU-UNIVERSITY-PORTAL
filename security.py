# security.py
import os
import re
from datetime import datetime, timedelta
import secrets
import string

# Password strength validation
def validate_password_strength(password):
    """Validate password meets security requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is strong"

# Generate secure random passwords
def generate_secure_password(length=12):
    """Generate a secure random password"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(characters) for _ in range(length))

# Session security
def validate_admin_session(session):
    """Validate admin session security"""
    if 'admin_id' not in session:
        return False, "Not logged in"
    
    if 'login_time' in session:
        login_time = datetime.fromisoformat(session['login_time'])
        if datetime.now() - login_time > timedelta(hours=2):
            return False, "Session expired"
    
    if 'ip_address' in session and session['ip_address'] != request.remote_addr:
        return False, "Session hijacking detected"
    
    return True, "Session valid"

# Rate limiting for login attempts
failed_attempts = {}

def check_login_attempts(ip_address, max_attempts=5, lockout_time=15):
    """Check if IP has exceeded login attempts"""
    now = datetime.now()
    
    if ip_address in failed_attempts:
        attempts, last_attempt = failed_attempts[ip_address]
        
        if now - last_attempt > timedelta(minutes=lockout_time):
            # Reset if lockout time has passed
            del failed_attempts[ip_address]
        elif attempts >= max_attempts:
            return False, f"Too many login attempts. Try again in {lockout_time} minutes."
    
    return True, "OK"

def record_failed_attempt(ip_address):
    """Record a failed login attempt"""
    now = datetime.now()
    
    if ip_address in failed_attempts:
        attempts, _ = failed_attempts[ip_address]
        failed_attempts[ip_address] = (attempts + 1, now)
    else:
        failed_attempts[ip_address] = (1, now)

def clear_login_attempts(ip_address):
    """Clear failed attempts on successful login"""
    if ip_address in failed_attempts:
        del failed_attempts[ip_address]