import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from server.main import app
except Exception as e:
    print(f"Error importing server.main: {e}")
    import traceback
    traceback.print_exc()
    raise
