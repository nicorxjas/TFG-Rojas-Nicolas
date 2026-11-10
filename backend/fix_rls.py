import psycopg2
import os
from services.supabase_rest import load_backend_env
from urllib.parse import urlparse

load_backend_env()
db_url = os.environ["DATABASE_URL"]

print("Connecting to database...")
conn = psycopg2.connect(db_url)
conn.autocommit = True
cursor = conn.cursor()

policy_sql = """
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'reports' AND policyname = 'Users can delete their own reports'
    ) THEN
        CREATE POLICY "Users can delete their own reports" ON reports
            FOR DELETE USING (auth.uid() = user_id);
        RAISE NOTICE 'Policy created';
    ELSE
        RAISE NOTICE 'Policy already exists';
    END IF;
END $$;
"""

print("Executing SQL to add DELETE policy...")
cursor.execute(policy_sql)
print("Policy added successfully!")

cursor.close()
conn.close()
