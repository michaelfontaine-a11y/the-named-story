"""
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
    FONTS_DIR              — Path to fonts directory (default: ./fonts)
    API_SECRET             — Simple auth token to protect your endpoint
    GELATO_API_KEY         — (Optional) Gelato API key for fetching exact cover dimensions
    GELATO_PRODUCT_UID     — (Optional) Gelato product UID for cover dimensions
"""

import os
import uuid
import tempfile
import shutil
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
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "")

GELATO_API_KEY  = os.environ.get("GELATO_API_KEY", "")
GELATO_PRODUCT  = os.environ.get("GELATO_PRODUCT_UID",
    "photobooks-hardcover_pf_210x280-mm-8x11-inch_pt_170-gsm-65lb-coated-silk_cl_4-4_ccl_4-4_bt_glued-left_ct_matt-lamination_prt_1-0_cpt_130-gsm-65-lb-cover-coated-silk_hor")

# Local path where we cache downloaded images from R2
IMAGES_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

# ============================================================
# VARIANT MAPPING — Short codes to internal folder names
# ============================================================
# Short codes (B1-B5, G1-G5) are used externally in Shopify, Make.com, URLs,
# and all customer-facing contexts. Internal folder names are NEVER exposed.
VARIANT_MAP = {
    "B1": "boy-fair-blonde",
    "B2": "boy-fair-red",
    "B3": "boy-olive-dark",
    "B4": "boy-tan-dark",
    "B5": "boy-deep-dark",
    "G1": "girl-fair-blonde",
    "G2": "girl-fair-red",
    "G3": "girl-olive-dark",
    "G4": "girl-tan-dark",
    "G5": "girl-deep-dark",
}

VALID_SHORT_CODES = list(VARIANT_MAP.keys())

# List of required image files per variant
REQUIRED_IMAGES = ["cover.jpg"] + [f"scene-{i:02d}.jpg" for i in range(1, 13)]


# ============================================================
# R2 CLIENT
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


# ============================================================
# R2 UPLOAD (for generated PDFs)
# ============================================================
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
# R2 DOWNLOAD (for illustration images)
# ============================================================
def download_variant_images(variant_folder):
    """
    Download all images for a variant from R2 to local filesystem.
    Images are cached — if they already exist locally, skip download.
    Returns the local variant directory path.
    """
    variant_dir = os.path.join(IMAGES_LOCAL, variant_folder)
    os.makedirs(variant_dir, exist_ok=True)

    # Check if all images already exist locally (cached from previous request)
    all_exist = all(
        os.path.exists(os.path.join(variant_dir, img))
        for img in REQUIRED_IMAGES
    )
    if all_exist:
        print(f"  Images for variant already cached locally")
        return variant_dir

    # Download from R2
    print(f"  Downloading images from R2...")
    client = get_r2_client()
    downloaded = 0

    for img_name in REQUIRED_IMAGES:
        local_path = os.path.join(variant_dir, img_name)
        r2_key = f"images/{variant_folder}/{img_name}"

        if os.path.exists(local_path):
            downloaded += 1
            continue

        try:
            client.download_file(R2_BUCKET, r2_key, local_path)
            downloaded += 1
        except Exception as e:
            print(f"  WARNING: Failed to download {r2_key}: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)

    print(f"  Downloaded {downloaded}/{len(REQUIRED_IMAGES)} images")

    # Verify all required images are now present
    missing = [img for img in REQUIRED_IMAGES if not os.path.exists(os.path.join(variant_dir, img))]
    if missing:
        raise FileNotFoundError(f"Missing images after download: {len(missing)} file(s)")

    return variant_dir


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
        "variant": "B1"                   (short code: B1-B5, G1-G5)
    }

    Returns:
    {
        "status": "success",
        "pdf_url": "https://pub-xxxxx.r2.dev/books/abc123.pdf",
        "cover_url": "https://pub-xxxxx.r2.dev/books/abc123-cover.pdf",
        "name": "Dominic",
        "variant": "B1",
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
    variant = data.get("variant", "").strip().upper()  # Normalize to uppercase

    # Validate inputs
    if not name:
        return jsonify({"status": "error", "message": "name is required"}), 400
    if not variant:
        return jsonify({"status": "error", "message": "variant is required"}), 400
    if len(name) > 20:
        return jsonify({"status": "error", "message": "name must be 20 characters or less"}), 400
    if variant not in VARIANT_MAP:
        return jsonify({
            "status": "error",
            "message": f"Invalid variant code. Must be one of: {VALID_SHORT_CODES}"
        }), 400

    # Translate short code to internal folder name (server-side only)
    variant_folder = VARIANT_MAP[variant]

    # Generate both PDFs
    try:
        # Step 1: Download images from R2 (cached if already present)
        download_variant_images(variant_folder)

        # Step 2: Generate interior PDF
        order_id = uuid.uuid4().hex[:12]
        # Use short code in filenames — never expose internal folder names
        base_name = f"{name.lower().replace(' ', '-')}-{variant}-{order_id}"

        interior_filename = f"{base_name}.pdf"
        interior_path = os.path.join(tempfile.gettempdir(), interior_filename)
        generate_book(name, gifter, variant_folder, interior_path)

        # Step 3: Generate cover wrap PDF
        cover_filename = f"{base_name}-cover.pdf"
        cover_path = os.path.join(tempfile.gettempdir(), cover_filename)
        generate_cover(
            name, variant_folder, cover_path,
            gelato_api_key=GELATO_API_KEY if GELATO_API_KEY else None,
            product_uid=GELATO_PRODUCT if GELATO_API_KEY else None,
            page_count=30
        )

        # Step 4: Upload both PDFs to R2
        pdf_url = upload_to_r2(interior_path, interior_filename)
        cover_url = upload_to_r2(cover_path, cover_filename)

        # Clean up temp PDF files
        for path in [interior_path, cover_path]:
            try:
                os.remove(path)
            except OSError:
                pass

        # Return short code in response — never internal folder name
        return jsonify({
            "status": "success",
            "pdf_url": pdf_url,
            "cover_url": cover_url,
            "name": name,
            "variant": variant,
            "pages": 30,
        })

    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
