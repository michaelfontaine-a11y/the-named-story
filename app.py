"""
The Named Story â Flask API Server
====================================
Wraps generate_book.py and generate_cover.py as a web API that Make.com can call.

Endpoints:
    POST /generate  â Generate a personalized book PDF + cover wrap PDF
    GET  /health    â Health check

Environment Variables:
    CLOUDFLARE_ACCOUNT_ID  â Your Cloudflare account ID
    CLOUDFLARE_ACCESS_KEY  â R2 access key ID
    CLOUDFLARE_SECRET_KEY  â R2 secret access key
    R2_BUCKET_NAME         â Your R2 bucket name (e.g. 'named-story-pdfs')
    R2_PUBLIC_URL          â Public URL for your R2 bucket (e.g. 'https://pub-xxxxx.r2.dev')
    IMAGES_BASE            â Path to images directory (default: ./images)
    FONTS_DIR              â Path to fonts directory (default: ./fonts)
    API_SECRET             â Simple auth token to protect your endpoint
    GELATO_API_KEY         â (Optional) Gelato API key for fetching exact cover dimensions
    GELATO_PRODUCT_UID     â (Optional) Gelato product UID for cover dimensions
"""

import os
import uuid
import tempfile
import boto3
from flask import Flask, request, jsonify
from generate_book import generate_book
from generate_cover import generate_cover

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

GELATO_API_KEY   = os.environ.get("GELATO_API_KEY", "")
GELATO_PRODUCT   = os.environ.get("GELATO_PRODUCT_UID",
    "photobooks-hardcover_pf_210x280-mm-8x11-inch_pt_170-gsm-65lb-coated-silk_cl_4-4_ccl_4-4_bt_glued-left_ct_matt-lamination_prt_1-0_cpt_130-gsm-65-lb-cover-coated-silk_hor")

# Valid character variants (10 total) â matches website codes B1-B5, G1-G5
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
    Generate a personalized book PDF and cover wrap PDF.

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
        "cover_url": "https://pub-xxxxx.r2.dev/books/abc123-cover.pdf",
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

    # Validate that required images exist for this variant
    images_base = os.environ.get("IMAGES_BASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "images"))
    variant_dir = os.path.join(images_base, variant)
    if not os.path.isdir(variant_dir):
        return jsonify({"status": "error", "message": f"Image folder not found for variant: {variant}"}), 400

    required_images = ["cover.jpg"] + [f"scene-{i:02d}.jpg" for i in range(1, 13)]
    missing = [img for img in required_images if not os.path.exists(os.path.join(variant_dir, img))]
    if missing:
        return jsonify({"status": "error", "message": f"Missing images for {variant}: {', '.join(missing)}"}), 400

    # Generate both PDFs
    order_id = uuid.uuid4().hex[:12]
    base_name = f"{name.lower().replace(' ', '-')}-{variant}-{order_id}"
    interior_filename = f"{base_name}.pdf"
    interior_path = os.path.join(tempfile.gettempdir(), interior_filename)
    cover_filename = f"{base_name}-cover.pdf"
    cover_path = os.path.join(tempfile.gettempdir(), cover_filename)

    try:
        # Interior pages
        generate_book(name, gifter, variant, interior_path)

        # Cover wrap
        generate_cover(
            name, variant, cover_path,
            gelato_api_key=GELATO_API_KEY if GELATO_API_KEY else None,
            product_uid=GELATO_PRODUCT if GELATO_API_KEY else None,
            page_count=30
        )

        # Upload both to R2
        pdf_url = upload_to_r2(interior_path, interior_filename)
        cover_url = upload_to_r2(cover_path, cover_filename)

        return jsonify({
            "status": "success",
            "pdf_url": pdf_url,
            "cover_url": cover_url,
            "name": name,
            "variant": variant,
            "pages": 30,
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        # Always clean up temp files
        for path in [interior_path, cover_path]:
            try:
                os.remove(path)
            except OSError:
                pass


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
The Named Story — Flask API Server
====================================
Wraps generate_book.py and generate_cover.py as a web API that Make.com can call.

Endpoints:
    POST /generate  — Generate a personalized book PDF + cover wrap PDF
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
    GELATO_API_KEY         — (Optional) Gelato API key for fetching exact cover dimensions
    GELATO_PRODUCT_UID     — (Optional) Gelato product UID for cover dimensions
"""

import os
import uuid
import tempfile
import boto3
from flask import Flask, request, jsonify
from generate_book import generate_book
from generate_cover import generate_cover

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

GELATO_API_KEY   = os.environ.get("GELATO_API_KEY", "")
GELATO_PRODUCT   = os.environ.get("GELATO_PRODUCT_UID",
    "photobooks-hardcover_pf_210x280-mm-8x11-inch_pt_170-gsm-65lb-coated-silk_cl_4-4_ccl_4-4_bt_glued-left_ct_matt-lamination_prt_1-0_cpt_130-gsm-65-lb-cover-coated-silk_hor")

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
    Generate a personalized book PDF and cover wrap PDF.

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
        "cover_url": "https://pub-xxxxx.r2.dev/books/abc123-cover.pdf",
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

    # Generate both PDFs
    try:
        order_id = uuid.uuid4().hex[:12]
        base_name = f"{name.lower().replace(' ', '-')}-{variant}-{order_id}"

        # Interior pages
        interior_filename = f"{base_name}.pdf"
        interior_path = os.path.join(tempfile.gettempdir(), interior_filename)
        generate_book(name, gifter, variant, interior_path)

        # Cover wrap
        cover_filename = f"{base_name}-cover.pdf"
        cover_path = os.path.join(tempfile.gettempdir(), cover_filename)
        generate_cover(
            name, variant, cover_path,
            gelato_api_key=GELATO_API_KEY if GELATO_API_KEY else None,
            product_uid=GELATO_PRODUCT if GELATO_API_KEY else None,
            page_count=30
        )

        # Upload both to R2
        pdf_url = upload_to_r2(interior_path, interior_filename)
        cover_url = upload_to_r2(cover_path, cover_filename)

        # Clean up temp files
        os.remove(interior_path)
        os.remove(cover_path)

        return jsonify({
            "status": "success",
            "pdf_url": pdf_url,
            "cover_url": cover_url,
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
