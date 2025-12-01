import os
from sqlalchemy import create_engine

url = os.getenv("DATABASE_URL", "postgresql+psycopg://spheraform:spheraform_dev@localhost:5432/spheraform")
print(f"Attempting to connect with URL: {url}")

engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute("SELECT current_database(), current_user")
    row = result.fetchone()
    print(f"Connected! Database: {row[0]}, User: {row[1]}")
