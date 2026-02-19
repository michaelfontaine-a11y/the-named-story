# The Named Story — Deployment Guide
## From Zero to Live API in One Afternoon

This guide assumes you've never deployed a server before. Every click is documented.

---

## WHAT YOU'RE BUILDING

A server that lives on the internet. When Make.com sends it a child's name + character variant, it generates a personalized 30-page PDF and returns a download URL. That URL goes to Gelato for printing.

**The files:**
- `generate_book.py` — The PDF generator (the brains)
- `app.py` — The web server wrapper (the door Make.com knocks on)
- `requirements.txt` — List of Python libraries needed
- `Procfile` — Tells Railway how to start the server
- `nixpacks.toml` — Tells Railway to use Python
- `fonts/` — Cormorant Garamond font files
- `images/` — Your illustration folders (one per variant)

---

## STEP 1: SET UP CLOUDFLARE R2 (Free Cloud Storage)
*Time: 15 minutes*

This is where your generated PDFs and illustration images will live.

### 1a. Create a Cloudflare account
1. Go to **https://dash.cloudflare.com/sign-up**
2. Sign up with email + password
3. You do NOT need to add a domain or website — just skip any onboarding prompts

### 1b. Enable R2 Storage
1. In the left sidebar, click **R2 Object Storage**
2. Click **Create bucket**
3. Bucket name: `named-story-pdfs`
4. Location: **Automatic** (it picks the fastest)
5. Click **Create bucket**

### 1c. Make the bucket publicly readable
1. Click into your `named-story-pdfs` bucket
2. Go to **Settings** tab
3. Under **Public access**, click **Allow Access** → enable the `r2.dev` subdomain
4. Copy the public URL it gives you — it looks like: `https://pub-abc123def456.r2.dev`
5. **Save this URL** — you'll need it later

### 1d. Create API credentials for R2
1. Go to **R2 Object Storage** → **Manage R2 API Tokens** (or find it under API tokens)
2. Click **Create API token**
3. Permissions: **Object Read & Write**
4. Specify bucket: `named-story-pdfs`
5. Click **Create API Token**
6. **Save these three values** (you only see them once):
   - **Account ID** (shown at top of R2 page, also in the URL)
   - **Access Key ID**
   - **Secret Access Key**

### 1e. Upload your illustration images to R2
1. In the bucket, create this folder structure by clicking **Upload** → **Create folder**:
   ```
   images/boy-light-light/
   images/boy-medium-brown/
   images/boy-dark-dark/
   images/boy-dark-brown/
   images/girl-light-light/
   images/girl-medium-brown/
   images/girl-dark-dark/
   images/girl-dark-brown/
   ```
2. Upload into each variant folder: `cover.png`, `scene-01.png` through `scene-12.png`
3. That's 13 images × 8 variants = 104 images total (you have 5 variants done, upload those now, add the rest later)

> **IMPORTANT:** The image filenames must be exactly: `cover.png`, `scene-01.png`, `scene-02.png`, ... `scene-12.png`

---

## STEP 2: SET UP GITHUB (Code Storage)
*Time: 10 minutes*

Railway deploys from GitHub. You push your code there, Railway automatically picks it up.

### 2a. Create a GitHub account (if you don't have one)
1. Go to **https://github.com/signup**
2. Create account with email + password

### 2b. Install GitHub Desktop (easiest option)
1. Go to **https://desktop.github.com/**
2. Download and install
3. Sign in with your GitHub account

### 2c. Create a new repository
1. In GitHub Desktop, click **File** → **New Repository**
2. Name: `the-named-story`
3. Local path: pick a folder on your computer (e.g. Desktop/the-named-story)
4. Check **Initialize with a README**
5. Click **Create Repository**

### 2d. Add the project files
1. Copy ALL the files I gave you into that folder:
   - `generate_book.py`
   - `app.py`
   - `requirements.txt`
   - `Procfile`
   - `nixpacks.toml`
   - `.gitignore`
2. Create a `fonts/` folder inside it and add:
   - `CormorantGaramond-Regular.ttf`
   - `CormorantGaramond-Italic.ttf`
   - `CormorantGaramond-Bold.ttf`
   - `CormorantGaramond-SemiBold.ttf`
   - `CormorantGaramond-BoldItalic.ttf`
   - (Download free from Google Fonts: https://fonts.google.com/specimen/Cormorant+Garamond — click "Download family")

> **NOTE:** You do NOT put the images folder in GitHub. Images live on R2 (too large for GitHub). The server will download them from R2.

### 2e. Push to GitHub
1. In GitHub Desktop, you should see all the new files listed
2. Type a commit message: "Initial commit - book generator"
3. Click **Commit to main**
4. Click **Publish repository**
5. Uncheck "Keep this code private" (or leave it private — both work with Railway)
6. Click **Publish Repository**

---

## STEP 3: DEPLOY ON RAILWAY
*Time: 15 minutes*

### 3a. Create a Railway account
1. Go to **https://railway.app/**
2. Click **Login** → **Login with GitHub**
3. Authorize Railway to access your GitHub

### 3b. Create a new project
1. Click **New Project**
2. Click **Deploy from GitHub repo**
3. Select your `the-named-story` repository
4. Railway will auto-detect Python and start building — **it will fail the first time.** That's fine. You need to add environment variables first.

### 3c. Add environment variables
1. Click on your service (the purple box)
2. Go to the **Variables** tab
3. Click **Raw Editor** and paste ALL of these:

```
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_ACCESS_KEY=your_access_key_here
CLOUDFLARE_SECRET_KEY=your_secret_key_here
R2_BUCKET_NAME=named-story-pdfs
R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
IMAGES_BASE=/tmp/images
FONTS_DIR=./fonts
API_SECRET=pick-a-long-random-string-here
PORT=5000
```

4. Replace the placeholder values with your actual Cloudflare R2 credentials from Step 1d
5. For `API_SECRET`, make up a long random string (e.g. `tns-2026-xK9mP3qR7wL2`) — this protects your API from random people using it
6. Click **Update Variables**

### 3d. Trigger a redeploy
1. Go to the **Deployments** tab
2. Click the three dots on the latest deployment → **Redeploy**
3. Wait 2-3 minutes for it to build
4. If it shows a green checkmark, you're live!

### 3e. Get your server URL
1. Go to **Settings** tab
2. Under **Networking** → **Public Networking**, click **Generate Domain**
3. Railway gives you a URL like: `https://the-named-story-production.up.railway.app`
4. **Save this URL** — this is what Make.com will call

### 3f. Test it!
Open a terminal (Mac: Terminal app, Windows: Command Prompt) and run:

```bash
curl -X POST https://YOUR-RAILWAY-URL/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR-API-SECRET" \
  -d '{"name": "Dominic", "gifter": "Grandma", "variant": "boy-dark-brown"}'
```

Or, if you don't like terminal, use **https://reqbin.com/**:
1. Method: POST
2. URL: `https://YOUR-RAILWAY-URL/generate`
3. Add header: `Authorization` = `Bearer YOUR-API-SECRET`
4. Add header: `Content-Type` = `application/json`
5. Body:
```json
{"name": "Dominic", "gifter": "Grandma & Grandpa", "variant": "boy-dark-brown"}
```
6. Click Send

**Expected response:**
```json
{
  "status": "success",
  "pdf_url": "https://pub-xxxxx.r2.dev/books/dominic-boy-dark-brown-abc123.pdf",
  "name": "Dominic",
  "variant": "boy-dark-brown",
  "pages": 30
}
```

Click that `pdf_url` — you should see a 30-page PDF with Dominic's name throughout.

---

## STEP 4: IMPORTANT NOTE ABOUT IMAGES

The current setup expects images to be on the server's local filesystem. For Railway deployment, we need the server to pull images from R2 instead. 

**Two options:**

**Option A (Simplest):** Put the images IN the GitHub repo. They'll deploy with the code. This works if your total image size is under ~500MB. Create an `images/` folder in your repo with all the variant subfolders.

**Option B (Scalable):** Keep images on R2, and modify the script to download them at startup. I can modify the script for this if you prefer.

**My recommendation:** Start with Option A. Push the images to GitHub for the variants you have done. It's simpler and Railway can handle it. We can migrate to Option B later if the repo gets too large.

---

## WHAT YOU NEED TO SAVE (REFERENCE CARD)

| Item | Value |
|------|-------|
| Railway URL | `https://__________________.up.railway.app` |
| API Secret | `_________________________________` |
| R2 Public URL | `https://pub-__________.r2.dev` |
| R2 Account ID | `_________________________________` |
| R2 Access Key | `_________________________________` |
| R2 Secret Key | `_________________________________` |
| GitHub Repo | `https://github.com/yourname/the-named-story` |

---

## NEXT STEPS AFTER DEPLOYMENT

Once your API is responding with PDFs:

1. **Wire up Make.com** — HTTP module calls your `/generate` endpoint
2. **Connect Gelato** — Make.com sends the PDF URL to Gelato's order API
3. **Connect Shopify** — Shopify order webhook triggers Make.com
4. **Build the landing page** — customer-facing site with checkout

All of that is covered in the separate Make.com automation guide.

---

## TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| Railway build fails | Check the build logs — usually a missing dependency. Make sure `requirements.txt` is in the root folder. |
| 401 Unauthorized | Your `Authorization: Bearer xxx` header doesn't match the `API_SECRET` env var |
| 500 error on /generate | Check Railway logs (click the deployment → Logs). Usually a missing image file or R2 credentials wrong. |
| PDF has placeholder boxes instead of images | Images not found at the expected path. Make sure they're in `images/{variant}/scene-01.png` etc. |
| Fonts look wrong (Helvetica instead of Garamond) | The `fonts/` folder is missing or font files aren't named correctly |
| R2 upload fails | Double-check your Account ID, Access Key, and Secret Key. Make sure the bucket name matches. |
| Railway costs money? | Railway free tier gives you $5/month of usage. Your API will use maybe $0.50/month at moderate volume. You won't need to pay until you're selling a LOT of books. |
