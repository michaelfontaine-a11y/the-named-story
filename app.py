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
from PyPDF2 import PdfReader, PdfWriter
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

REQUIRED_IMAGES = ["cover.jpg"] + [f"scene-{i:02d}.jpg" for i in range(1, 13)]


# ============================================================
# R2 CLIENT
# ============================================================
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )


# ============================================================
# R2 UPLOAD
# ============================================================
def upload_to_r2(local_path, filename):
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
    variant_dir = os.path.join(IMAGES_LOCAL, variant_folder)
    os.makedirs(variant_dir, exist_ok=True)

    all_exist = all(
        os.path.exists(os.path.join(variant_dir, img))
        for img in REQUIRED_IMAGES
    )
    if all_exist:
        print(f"  Images for variant already cached locally")
        return variant_dir

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

    missing = [img for img in REQUIRED_IMAGES if not os.path.exists(os.path.join(variant_dir, img))]
    if missing:
        raise FileNotFoundError(f"Missing images after download: {len(missing)} file(s)")

    return variant_dir


# ============================================================
# PDF MERGER — Combine cover + interior for Gelato
# ============================================================
def create_combined_pdf(cover_path, interior_path, output_path):
    """
    Merge cover wrap + interior into a single PDF for Gelato.

    Gelato photobooks require ONE PDF structured as:
      Page 1:     Cover wrap spread (front + spine + back)
      Page 2:     Blank endpaper
      Pages 3-32: 30 interior content pages
      Page 33:    Blank endpaper

    See: https://support.gelato.com/en/articles/8996282
    """
    writer = PdfWriter()

    # Page 1: Cover wrap spread
    cover_reader = PdfReader(cover_path)
    writer.add_page(cover_reader.pages[0])

    # Page 2: Blank endpaper (matching interior page dimensions)
    interior_reader = PdfReader(interior_path)
    page0 = interior_reader.pages[0]
    iw = float(page0.mediabox.width)
    ih = float(page0.mediabox.height)
    writer.add_blank_page(width=iw, height=ih)

    # Pages 3 to N+2: All interior pages
    for page in interior_reader.pages:
        writer.add_page(page)

    # Last page: Blank endpaper
    writer.add_blank_page(width=iw, height=ih)

    with open(output_path, 'wb') as f:
        writer.write(f)

    total = len(writer.pages)
    print(f"  Combined PDF: {total} pages ({output_path})")
    return total


# ============================================================
# AUTH MIDDLEWARE
# ============================================================
def check_auth():
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
    Generate a personalized book as a single combined PDF for Gelato.

    Expected JSON body:
    {
        "name": "Dominic",
        "gifter": "Grandma & Grandpa",
        "variant": "B1"
    }

    Returns:
    {
        "status": "success",
        "combined_url": "https://pub-xxxxx.r2.dev/books/abc123-combined.pdf",
        "pdf_url": "https://pub-xxxxx.r2.dev/books/abc123.pdf",
        "cover_url": "https://pub-xxxxx.r2.dev/books/abc123-cover.pdf",
        "name": "Dominic",
        "variant": "B1",
        "pages": 33
    }
    """
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "JSON body required"}), 400

    name    = data.get("name", "").strip()
    gifter  = data.get("gifter", "").strip()
    variant = data.get("variant", "").strip().upper()

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

    variant_folder = VARIANT_MAP[variant]

    try:
        # Step 1: Download images from R2
        download_variant_images(variant_folder)

        # Step 2: Generate interior PDF (30 pages)
        order_id = uuid.uuid4().hex[:12]
        base_name = f"{name.lower().replace(' ', '-')}-{variant}-{order_id}"

        interior_filename = f"{base_name}.pdf"
        interior_path = os.path.join(tempfile.gettempdir(), interior_filename)
        generate_book(name, gifter, variant_folder, interior_path)

        # Step 3: Generate cover wrap PDF (1 page)
        cover_filename = f"{base_name}-cover.pdf"
        cover_path = os.path.join(tempfile.gettempdir(), cover_filename)
        generate_cover(
            name, variant_folder, cover_path,
            gelato_api_key=GELATO_API_KEY if GELATO_API_KEY else None,
            product_uid=GELATO_PRODUCT if GELATO_API_KEY else None,
            page_count=30
        )

        # Step 4: Merge into single combined PDF for Gelato
        #   Page 1:     Cover wrap spread
        #   Page 2:     Blank endpaper
        #   Pages 3-32: Interior pages
        #   Page 33:    Blank endpaper
        combined_filename = f"{base_name}-combined.pdf"
        combined_path = os.path.join(tempfile.gettempdir(), combined_filename)
        total_pages = create_combined_pdf(cover_path, interior_path, combined_path)

        # Step 5: Upload all PDFs to R2
        combined_url = upload_to_r2(combined_path, combined_filename)
        pdf_url = upload_to_r2(interior_path, interior_filename)
        cover_url = upload_to_r2(cover_path, cover_filename)

        # Clean up temp files
        for path in [interior_path, cover_path, combined_path]:
            try:
                os.remove(path)
            except OSError:
                pass

        return jsonify({
            "status": "success",
            "combined_url": combined_url,
            "pdf_url": pdf_url,
            "cover_url": cover_url,
            "name": name,
            "variant": variant,
            "pages": total_pages,
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
