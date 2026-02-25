"""
The Named Story — Flask API Server
====================================
Wraps generate_book.py as a web API that Make.com can call.

Endpoints:
    POST /generate  — Generate a personalized book PDF
    GET  /health    — Health check

Environment Variables:
    CLOUDFLARE_ACCOUNT_ID  — Your Cloudflare account ID
    CLOUDFLARE_ACCESS_KEY  — R2 access key ID
    CLOUDFLARE_SECRET_KEY  — R2 secret access key
    R2_BUCKET_NAME         — Your R2 bucket name (e.g. 'named-story-pdfs')
    R2_PUBLIC_URL          — Public URL for your R2 bucket (e.g. 'https://pub-xxxxx.r2.dev')
    IMAGES_BASE            — Path to images directory (default: ./images)
    FONTS_DIR              — Path to fonts directory (default: ./fonts)
    API_SECRET             — Simple auth token to protect your endpoint
"""

import os
import uuid
import tempfile
import boto3
from flask import Flask, request, jsonify
from generate_book import generate_book

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
API_SECRET = os.environ.get("API_SECRET", "change-me-before-deploy")

R2_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
R2_ACCESS_KEY = os.environ.get("CLOUDFLARE_ACCESS_KEY", "")
R2_SECRET_KEY = os.environ.get("CLOUDFLARE_SECRET_KEY", "")
R2_BUCKET     = os.environ.get("R2_BUCKET_NAME", "named-story-pdfs")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")  # e.g. https://pub-xxxxx.r2.dev

# Valid character variants (10 total) — matches website codes B1-B5, G1-G5
VALID_VARIANTS = [
    "boy-fair-blonde",     # B1
    "boy-fair-red",        # B2
    "boy-olive-dark",      # B3
    "boy-tan-dark",        # B4
    "boy-deep-dark",       # B5
    "girl-fair-blonde",    # G1
    "girl-fair-red",       # G2
    "girl-olive-dark",     # G3
    "girl-tan-dark",       # G4
    "girl-deep-dark",      # G5
]


# ============================================================
# R2 UPLOAD
# ============================================================
def get_r2_client():
    """Create an S3-compatible client for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )


def upload_to_r2(local_path, filename):
    """Upload a file to R2 and return the public URL."""
    client = get_r2_client()
    key = f"books/{filename}"
    client.upload_file(
        local_path, R2_BUCKET, key,
        ExtraArgs={"ContentType": "application/pdf"},
    )
    return f"{R2_PUBLIC_URL}/{key}"


# ============================================================
# AUTH MIDDLEWARE
# ============================================================
def check_auth():
    """Simple bearer token auth."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return auth.split("Bearer ")[1].strip() == API_SECRET


# ============================================================
# ROUTES
# ============================================================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "the-named-story-generator"})


@app.route("/generate", methods=["POST"])
def generate():
    """
    Generate a personalized book PDF.

    Expected JSON body:
    {
        "name": "Dominic",
        "gifter": "Grandma & Grandpa",   (optional, default "")
        "variant": "boy-fair-blonde"
    }

    Returns:
    {
        "status": "success",
        "pdf_url": "https://pub-xxxxx.r2.dev/books/abc123.pdf",
        "name": "Dominic",
        "variant": "boy-fair-blonde",
        "pages": 30
    }
    """
    # Auth check
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Parse request
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "JSON body required"}), 400

    name    = data.get("name", "").strip()
    gifter  = data.get("gifter", "").strip()
    variant = data.get("variant", "").strip()

    # Validate
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    if not variant:
        return jsonify({"status": "error", "message": "variant is required"}), 400
    if len(name) > 20:
        return jsonify({"status": "error", "message": "name must be 20 characters or less"}), 400

    if variant not in VALID_VARIANTS:
        return jsonify({"status": "error", "message": f"Invalid variant. Must be one of: {VALID_VARIANTS}"}), 400

    # Generate PDF
    try:
        order_id = uuid.uuid4().hex[:12]
        filename = f"{name.lower().replace(' ', '-')}-{variant}-{order_id}.pdf"
        tmp_path = os.path.join(tempfile.gettempdir(), filename)

        generate_book(name, gifter, variant, tmp_path)

        # Upload to R2
        pdf_url = upload_to_r2(tmp_path, filename)

        # Clean up temp file
        os.remove(tmp_path)

        return jsonify({
            "status": "success",
            "pdf_url": pdf_url,
            "name": name,
            "variant": variant,
            "pages": 30,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
