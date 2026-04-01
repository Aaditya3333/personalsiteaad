import sys
import os
sys.path.insert(0, '.')

# Test each component individually
print("Testing application components...")

try:
    print("1. Testing imports...")
    from main import app, init_db, get_db_connection, get_visitor_count, increment_visitor
    print("   ✓ All imports successful")
    
    print("2. Testing database initialization...")
    init_db()
    print("   ✓ Database initialization successful")
    
    print("3. Testing visitor count...")
    count = get_visitor_count()
    print(f"   ✓ Visitor count: {count}")
    
    print("4. Testing visitor increment...")
    increment_visitor()
    print("   ✓ Visitor increment successful")
    
    print("5. Testing template response...")
    from fastapi import Request
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    response = client.get("/")
    print(f"   ✓ Home page response: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✓ Application is working correctly!")
    else:
        print(f"   ✗ Error response: {response.text}")
        
except Exception as e:
    print(f"   ✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
