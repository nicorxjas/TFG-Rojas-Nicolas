import psycopg2
import os
from services.supabase_rest import load_backend_env

load_backend_env()

db_urls = [os.environ["DATABASE_URL"]]

# Get migration SQL file path
current_dir = os.path.dirname(__file__)
migration_path = os.path.join(os.path.dirname(current_dir), "supabase", "migrations", "03_dynamic_templates_blocks.sql")

if not os.path.exists(migration_path):
    print(f"Error: Migration file not found at {migration_path}")
    exit(1)

with open(migration_path, "r", encoding="utf-8") as f:
    sql = f.read()

print("Connecting to Supabase PostgreSQL database...")
conn = None
last_err = None
for url in db_urls:
    try:
        print(f"Trying connection with: {url.split('@')[-1]}")
        conn = psycopg2.connect(url)
        conn.autocommit = True
        break
    except Exception as e:
        last_err = e
        print(f"Connection failed for this URL: {e}")

if not conn:
    print(f"[Error] Connecting to DB failed: {last_err}")
    exit(1)

try:
    cursor = conn.cursor()
    print("Executing migration 03_dynamic_templates_blocks.sql...")
    cursor.execute(sql)
    print("[Success] Migration executed successfully! Added 'blocks' column to report_templates and migrated seeds.")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"[Error] Error executing migration SQL: {e}")
    exit(1)
