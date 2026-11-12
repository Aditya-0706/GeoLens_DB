
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            cloudinary_url TEXT NOT NULL,
            cloudinary_public_id VARCHAR(255) NOT NULL,
            file_hash CHAR(64) NOT NULL UNIQUE,
            file_size BIGINT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    print("Successfully connected to Aiven!")
    print("Images table created successfully!")

except mysql.connector.Error as error:
    print("Database error:", error)

finally:
    if 'cursor' in locals():
        cursor.close()

    if 'conn' in locals() and conn.is_connected():
        conn.close()
