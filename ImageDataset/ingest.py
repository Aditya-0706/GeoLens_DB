
import os
import zipfile
import hashlib
import mimetypes
import time

from pathlib import Path
from dotenv import load_dotenv

import mysql.connector

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ==================================
# CONFIGURATION
# ==================================

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

ZIP_PATH = BASE_DIR / "dataset.zip"
EXTRACT_DIR = BASE_DIR / "extracted"

CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.file"
]

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png",
    ".webp", ".bmp", ".gif", ".tiff"
}


# ==================================
# 1. MYSQL CONNECTION
# ==================================

def connect_mysql():

    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE"),

        ssl_ca=os.getenv("MYSQL_SSL_CA"),
        ssl_verify_cert=True,
        ssl_verify_identity=True
    )

    print("Connected to Aiven MySQL!")

    return conn


# ==================================
# 2. GOOGLE DRIVE AUTHENTICATION
# ==================================

def connect_google_drive():

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            "credentials.json not found in project folder!"
        )

    creds = None

    if TOKEN_FILE.exists():

        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:

            creds.refresh(Request())

        else:

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE),
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    service = build(
        "drive",
        "v3",
        credentials=creds
    )

    print("Google Drive connected successfully!")

    return service


# ==================================
# 3. EXTRACT ZIP FILE
# ==================================

def extract_images():

    if not ZIP_PATH.exists():
        raise FileNotFoundError(
            "dataset.zip not found!"
        )

    EXTRACT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    root = EXTRACT_DIR.resolve()

    with zipfile.ZipFile(ZIP_PATH, "r") as archive:

        for member in archive.infolist():

            target = (
                EXTRACT_DIR / member.filename
            ).resolve()

            if not target.is_relative_to(root):
                raise ValueError(
                    "Unsafe ZIP entry detected!"
                )

            if member.is_dir():
                target.mkdir(
                    parents=True,
                    exist_ok=True
                )
                continue

            target.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with archive.open(member) as source:

                with open(target, "wb") as destination:

                    while True:

                        chunk = source.read(1024 * 1024)

                        if not chunk:
                            break

                        destination.write(chunk)

    print("ZIP extraction completed!")


# ==================================
# 4. FIND ALL IMAGES
# ==================================

def find_images():

    images = [
        path
        for path in EXTRACT_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
    ]

    images.sort()

    print("Total images found:", len(images))

    return images


# ==================================
# 5. GENERATE IMAGE HASH
# ==================================

def calculate_hash(path):

    sha = hashlib.sha256()

    with open(path, "rb") as file:

        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b""
        ):

            sha.update(chunk)

    return sha.hexdigest()


# ==================================
# 6. GET EXISTING MYSQL HASHES
# ==================================

def get_existing_hashes(conn):

    cursor = conn.cursor()

    cursor.execute(
        "SELECT file_hash FROM images"
    )

    hashes = {
        row[0]
        for row in cursor.fetchall()
        if row[0]
    }

    cursor.close()

    return hashes


# ==================================
# 7. UPLOAD IMAGE TO DRIVE
# ==================================

def upload_image(service, path):

    mime_type, _ = mimetypes.guess_type(
        str(path)
    )

    metadata = {
        "name": path.name
    }

    media = MediaFileUpload(
        str(path),
        mimetype=mime_type or "application/octet-stream",
        resumable=True
    )

    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id,webViewLink"
    ).execute(num_retries=3)

    drive_id = result["id"]

    drive_url = (
        f"https://drive.google.com/file/d/{drive_id}/view"
    )

    return drive_id, drive_url


# ==================================
# 8. SAVE RECORD IN MYSQL
# ==================================

def save_image(conn, path, drive_id, drive_url, digest):

    cursor = conn.cursor()

    query = """
        INSERT INTO images
        (
            filename,
            drive_file_id,
            drive_url,
            image_path,
            file_hash,
            file_size
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id = id
    """

    values = (
        path.name,
        drive_id,
        drive_url,
        str(path),
        digest,
        path.stat().st_size
    )

    cursor.execute(query, values)

    conn.commit()

    cursor.close()


# ==================================
# 9. MAIN INGESTION PROCESS
# ==================================

def main():

    print("\n===== IMAGE INGESTION STARTED =====\n")

    extract_images()

    images = find_images()

    if not images:
        raise RuntimeError(
            "No supported images found!"
        )

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            "Please add credentials.json first."
        )

    conn = connect_mysql()

    try:

        service = connect_google_drive()

        existing_hashes = get_existing_hashes(conn)

        uploaded = 0
        skipped = 0
        failed = 0

        for index, path in enumerate(images, start=1):

            digest = calculate_hash(path)

            if digest in existing_hashes:

                print(
                    f"[{index}/{len(images)}] "
                    f"Already exists: {path.name}"
                )

                skipped += 1
                continue

            try:

                drive_id, drive_url = upload_image(
                    service,
                    path
                )

                save_image(
                    conn,
                    path,
                    drive_id,
                    drive_url,
                    digest
                )

                existing_hashes.add(digest)

                uploaded += 1

                print(
                    f"[{index}/{len(images)}] "
                    f"Uploaded: {path.name}"
                )

            except Exception as error:

                failed += 1

                print(
                    f"[{index}/{len(images)}] "
                    f"Failed: {path.name}"
                )

                print("Reason:", error)

                time.sleep(2)

        print("\n===== FINAL SUMMARY =====")

        print("Total images:", len(images))
        print("Uploaded:", uploaded)
        print("Skipped:", skipped)
        print("Failed:", failed)

        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM images"
        )

        total = cursor.fetchone()[0]

        print("Total MySQL records:", total)

        cursor.close()

    finally:

        conn.close()

        print("\nMySQL connection closed.")


if __name__ == "__main__":
    main()
