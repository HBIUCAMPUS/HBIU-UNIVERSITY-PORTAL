from database import get_db, init_db
import sqlite3
import os

def diagnose_admin_login_issue():
    print("=== Diagnosing Admin Login Issue ===\n")
    
    # Check if we're using SQLite or PostgreSQL
    if os.environ.get('DATABASE_URL'):
        print("Database: PostgreSQL (Production)")
    else:
        print("Database: SQLite (Development)")
    
    # Initialize database
    print("\n1. Initializing database...")
    try:
        init_db()
        print("✓ Database initialization completed")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return
    
    # Check admins table structure
    print("\n2. Checking admins table structure...")
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'admins' 
                ORDER BY ordinal_position
            """)
        else:
            cursor.execute("PRAGMA table_info(admins)")
        
        columns = cursor.fetchall()
        print("Admins table columns:")
        for col in columns:
            print(f"  - {col}")
        
        # Check if is_active column exists
        column_names = [col[1] if not os.environ.get('DATABASE_URL') else col[0] for col in columns]
        if 'is_active' in column_names:
            print("✓ is_active column exists")
        else:
            print("✗ is_active column missing")
            
    except Exception as e:
        print(f"✗ Error checking table structure: {e}")
    
    # Check if any admin accounts exist
    print("\n3. Checking admin accounts...")
    try:
        if os.environ.get('DATABASE_URL'):
            cursor.execute("SELECT id, email, role, is_active FROM admins")
        else:
            cursor.execute("SELECT id, email, role, is_active FROM admins")
        
        admins = cursor.fetchall()
        if admins:
            print("Admin accounts found:")
            for admin in admins:
                print(f"  - ID: {admin[0]}, Email: {admin[1]}, Role: {admin[2]}, Active: {admin[3]}")
        else:
            print("✗ No admin accounts found")
            print("  Creating a default admin account...")
            create_default_admin()
            
    except Exception as e:
        print(f"✗ Error checking admin accounts: {e}")
        print("  Attempting to create default admin account...")
        create_default_admin()
    
    # Test the verify_admin function
    print("\n4. Testing verify_admin function...")
    try:
        from database import verify_admin
        
        # Test with a non-existent email first
        test_admin = verify_admin('test@test.com', 'password')
        if test_admin:
            print("✗ verify_admin returned result for non-existent user (unexpected)")
        else:
            print("✓ verify_admin correctly returned None for non-existent user")
            
    except Exception as e:
        print(f"✗ verify_admin function error: {e}")
    
    conn.close()
    print("\n=== Diagnosis Complete ===")

def create_default_admin():
    """Create a default admin account if none exists"""
    from database import create_admin
    try:
        success = create_admin('admin@university.edu', 'admin123')
        if success:
            print("✓ Default admin account created: admin@university.edu / admin123")
        else:
            print("✗ Failed to create default admin account")
    except Exception as e:
        print(f"✗ Error creating default admin: {e}")

if __name__ == "__main__":
    diagnose_admin_login_issue()