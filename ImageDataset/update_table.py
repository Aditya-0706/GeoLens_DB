
import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    port=int(os.getenv("MYSQL_PORT")),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DATABASE"),
    ssl_ca=os.getenv("MYSQL_SSL_CA"),
    ssl_verify_cert=True,
    ssl_verify_identity=True
)

cursor = conn.cursor()

# Check existing columns
cursor.execute("SHOW COLUMNS FROM images")

existing_columns = {
    row[0] for row in cursor.fetchall()
}

# Make Cloudinary columns optional
if "cloudinary_url" in existing_columns:
    cursor.execute("""
        ALTER TABLE images
        MODIFY cloudinary_url TEXT NULL
    """)

if "cloudinary_public_id" in existing_columns:
    cursor.execute("""
        ALTER TABLE images
        MODIFY cloudinary_public_id VARCHAR(255) NULL
    """)

# Add missing Google Drive columns
new_columns = {
    "drive_file_id": "VARCHAR(255) NULL",
    "drive_url": "TEXT NULL",
    "image_path": "TEXT NULL"
}

for column, definition in new_columns.items():

    if column not in existing_columns:

        cursor.execute(
            f"ALTER TABLE images ADD COLUMN {column} {definition}"
        )

        print(f"Added column: {column}")

    else:
        print(f"Column already exists: {column}")

conn.commit()

print("\nMySQL table updated successfully!")

cursor.close()
conn.close()
