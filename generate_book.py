"""
The Named Story — PDF Book Generator
=====================================
Generates personalized 30-page print-ready PDFs for "[Child's Name] and the First Easter"
Replaces CraftMyPDF entirely. $0/month.

Usage:
    python generate_book.py --name "Dominic" --gifter "Grandma & Grandpa" --variant "boy-dark-brown"

Image Setup:
    Put illustrations in: ./images/{variant}/
    Files: cover.jpg, scene-01.jpg through scene-12.jpg
    Resolution: 3300x2400px (300 DPI at 11x8")
    Format: JPEG at 95% quality (converted from PNG for file size)
"""

import os
import argparse
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ============================================================
# PAGE DIMENSIONS (match Gelato product spec)
# ============================================================
PAGE_W = 11 * inch
PAGE_H = 8 * inch


# ============================================================
# COLORS — Warm palette matching the book aesthetic
# ============================================================
CREAM      = HexColor("#fdf6ec")
DARK_BROWN = HexColor("#3d2b1f")
WARM_BROWN = HexColor("#5a3a10")
GOLD       = HexColor("#c9a96e")
SOFT_GREY  = HexColor("#999999")
WHITE      = HexColor("#ffffff")


# ============================================================
# TYPOGRAPHY SETTINGS
# ============================================================
BODY_SIZE    = 14.5
BODY_LEADING = BODY_SIZE * 1.72
PARA_SPACE   = BODY_LEADING * 0.45
ML = 1.6 * inch   # margin left
MR = 1.6 * inch   # margin right
MT = 1.4 * inch   # margin top
MB = 1.0 * inch   # margin bottom
TW = PAGE_W - ML - MR  # text width

# Font names (will be overridden if custom fonts not found)
F_REG  = "BookSerif"
F_IT   = "BookSerif-Italic"
F_BOLD = "BookSerif-Bold"
F_SEMI = "BookSerif-SemiBold"


# ============================================================
# PRONOUNS
# ============================================================
PN = {
    "boy":  {"he": "he", "He": "He", "him": "him", "his": "his", "His": "His", "himself": "himself"},
    "girl": {"he": "she", "He": "She", "him": "her", "his": "her", "His": "Her", "himself": "herself"},
}


# ============================================================
# FONT SETUP — Cormorant Garamond (elegant book serif)
# ============================================================
FONTS_DIR = os.environ.get("FONTS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"))


def register_fonts():
    global F_REG, F_IT, F_BOLD, F_SEMI
    fonts = {
        F_REG:  "CormorantGaramond-Regular.ttf",
        F_IT:   "CormorantGaramond-Italic.ttf",
        F_BOLD: "CormorantGaramond-Bold.ttf",
        F_SEMI: "CormorantGaramond-SemiBold.ttf",
        "BookSerif-BoldItalic": "CormorantGaramond-BoldItalic.ttf",
    }
    ok = True
    for name, fn in fonts.items():
        p = os.path.join(FONTS_DIR, fn)
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont(name, p))
        else:
            ok = False
    if not ok:
        F_REG = "Helvetica"
        F_IT = "Helvetica-Oblique"
        F_BOLD = "Helvetica-Bold"
        F_SEMI = "Helvetica-Bold"
        print("Warning: Custom fonts not found in '{}', using Helvetica fallback".format(FONTS_DIR))


# ============================================================
# TEXT HELPERS
# ============================================================
def wrap(c, text, font, size, max_w):
    """Word-wrap text into lines that fit within max_w."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = f"{cur} {w}" if cur else w
        if c.stringWidth(t, font, size) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ============================================================
# PAGE RENDERERS
# ============================================================

def pg_blank(c):
    """Plain cream page."""
    c.setFillColor(CREAM)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def pg_image(c, path):
    """Full-bleed illustration page."""
    if os.path.exists(path):
        c.drawImage(path, 0, 0, width=PAGE_W, height=PAGE_H, preserveAspectRatio=False)
    else:
        # Placeholder for missing images
        c.setFillColor(HexColor("#f0e6d3"))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(SOFT_GREY)
        c.setFont("Helvetica", 11)
        c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 8, f"[ {os.path.basename(path)} ]")
        c.setFont("Helvetica", 9)
        c.drawCentredString(PAGE_W / 2, PAGE_H / 2 - 8, "3300\u00d72400px JPG @ 300 DPI")


def pg_cover(c, data, img_path):
    """Cover page — full-bleed image with title overlay."""
    pg_image(c, img_path)
    c.setFillColor(WHITE)
    c.setFont(F_BOLD, 42)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 1.1 * inch, data["t1"])
    c.drawCentredString(PAGE_W / 2, PAGE_H - 1.75 * inch, data["t2"])
    c.setFont(F_IT, 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 2.35 * inch, data["sub"])


def pg_dedication(c, lines):
    """Dedication page — centered, warm, intimate."""
    pg_blank(c)
    total = sum(30 if l else 22 for l in lines)
    y = (PAGE_H + total) / 2
    c.setFillColor(WARM_BROWN)
    for line in lines:
        if not line:
            y -= 22
            continue
        if line.startswith("\u201c") or line.startswith('"'):
            c.setFont(F_IT, 14)
        elif line.startswith("for ") or line.startswith("from "):
            c.setFont(F_SEMI, 17)
        else:
            c.setFont(F_REG, 17)
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 30


def pg_text(c, paragraphs):
    """Standard story text page with decorative divider."""
    pg_blank(c)
    y = PAGE_H - MT
    for para in paragraphs:
        if not para.strip():
            y -= BODY_LEADING
            continue
        is_q = para.lstrip().startswith("\u201c") or para.lstrip().startswith('"')
        font = F_IT if is_q else F_REG
        c.setFont(font, BODY_SIZE)
        c.setFillColor(DARK_BROWN)
        for line in wrap(c, para, font, BODY_SIZE, TW):
            if y < MB:
                break
            c.drawString(ML, y, line)
            y -= BODY_LEADING
        y -= PARA_SPACE
    # Decorative divider
    c.setFillColor(GOLD)
    c.setFont(F_REG, 18)
    c.drawCentredString(PAGE_W / 2, MB - 0.15 * inch, "\u2726")


def pg_finale(c, data, img_path):
    """The big emotional payoff — spread 12 finale text, centered and special.
    Uses tighter spacing than normal text pages to fit the longer finale content."""
    pg_blank(c)
    # Tighter layout for the finale — more text needs to fit on this page
    fin_size = 13
    fin_leading = fin_size * 1.6
    fin_para_space = fin_leading * 0.35
    fin_mt = 1.1 * inch
    fin_mb = 0.8 * inch

    y = PAGE_H - fin_mt
    c.setFillColor(DARK_BROWN)
    for para in data:
        if not para.strip():
            y -= fin_leading
            continue
        # Handle multi-line paragraphs (for the Jesus quote)
        sub_lines = para.split("\n")
        for sub in sub_lines:
            if not sub.strip():
                y -= fin_leading * 0.5
                continue
            is_q = sub.lstrip().startswith("\u201c") or sub.lstrip().startswith('"')
            font = F_IT if is_q else F_REG
            c.setFont(font, fin_size)
            for line in wrap(c, sub, font, fin_size, TW):
                if y < fin_mb:
                    break
                c.drawString(ML, y, line)
                y -= fin_leading
        y -= fin_para_space
    # Gold divider
    c.setFillColor(GOLD)
    c.setFont(F_REG, 18)
    c.drawCentredString(PAGE_W / 2, fin_mb - 0.15 * inch, "\u2726")


def pg_promo(c, lines):
    """Back promo page — 'More adventures coming soon...'"""
    pg_blank(c)
    y = PAGE_H / 2 + 0.5 * inch
    for line in lines:
        if not line:
            y -= 24
            continue
        if "THE NAMED STORY" in line:
            c.setFont(F_REG, 14)
            c.setFillColor(GOLD)
        else:
            c.setFont(F_IT, 17)
            c.setFillColor(WARM_BROWN)
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 36


def pg_copyright(c, lines):
    """Copyright / Isaiah 43:1 page."""
    pg_blank(c)
    y = PAGE_H / 2 + 0.5 * inch
    for line in lines:
        if not line:
            y -= 24
            continue
        if "ISAIAH" in line:
            c.setFont(F_BOLD, 13)
            c.setFillColor(WARM_BROWN)
        elif "\u00a9" in line:
            c.setFont(F_REG, 10)
            c.setFillColor(SOFT_GREY)
        else:
            c.setFont(F_IT, 16)
            c.setFillColor(WARM_BROWN)
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 28


# ============================================================
# BOOK CONTENT — The Full Story
# ============================================================

def build_book(name, gifter, variant):
    """Build the complete 30-page book structure with personalized text."""
    gender = "girl" if variant.startswith("girl") else "boy"
    p = PN[gender]
    he = p["he"]
    He = p["He"]
    him = p["him"]
    his = p["his"]
    His = p["His"]
    himself = p["himself"]

    img_dir = os.path.join(
        os.environ.get("IMAGES_BASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")),
        variant
    )
    img = lambda f: os.path.join(img_dir, f)

    pages = [
        # --- PAGE 1: Cover ---
        ("cover", img("cover.jpg"), {
            "t1": f"{name} and the",
            "t2": "First Easter",
            "sub": "A Named Story Book",
        }),

        # --- PAGE 2: Blank (inside front) ---
        ("blank",),

        # --- PAGE 3: Dedication ---
        ("dedication", [
            "This story was made with love",
            f"for {name}",
            f"from {gifter}" if gifter else "",
            "",
            "\u201cBecause some stories are so important,",
            "you deserve to be inside them.\u201d",
        ]),

        # --- PAGE 4: Illustration — Road to Jerusalem ---
        ("image", img("scene-01.jpg")),

        # --- PAGE 5: Text — Spread 1 ---
        ("text", [
            "The road was dusty and long, and the sun hung low like a lantern someone had forgotten to put away.",
            f"{name} didn\u2019t know how {he}\u2019d gotten here \u2014 only that the air smelled like warm bread and wild sage, and that something important was waiting at the end of this road.",
            "Up ahead, a city sat on a hilltop, glowing gold in the late-afternoon light. People were walking toward it from every direction, like rivers flowing to the sea.",
            f"{name} took a deep breath and followed.",
        ]),

        # --- PAGE 6: Illustration — Palm Sunday ---
        ("image", img("scene-02.jpg")),

        # --- PAGE 7: Text — Spread 2 ---
        ("text", [
            "The city was full of singing.",
            "People crowded the narrow streets, waving branches torn from palm trees, throwing their coats on the ground like the road itself should be dressed for a celebration. Children climbed walls to get a better look. Someone was laughing so hard they were crying.",
            f"Someone handed {name} a palm branch. {He} waved it so hard it nearly flew out of {his} hands.",
            f"The crowd was shouting a name, over and over, but it was so loud and {name} was so small that the word got lost somewhere above {his} head.",
            f"{He} didn\u2019t know what everyone was celebrating yet. But {he} could feel it \u2014 something wonderful had come to this city, and the whole world knew it except {him}.",
        ]),

        # --- PAGE 8: Illustration — Seeing Jesus through crowd ---
        ("image", img("scene-03.jpg")),

        # --- PAGE 9: Text — Spread 3 ---
        ("text", [
            f"And then {name} saw Him.",
            f"Through a gap in the crowd \u2014 between elbows and shoulders and people who were much, much taller \u2014 there was a man who seemed to glow the way the last bit of sunlight glows before it slips behind a mountain.",
            f"{name} stood on {his} tiptoes.",
            f"The man turned. And He looked right at {name}.",
            f"Not past {him}. Not over {his} head. Not through {him} the way busy grown-ups sometimes do. At {him}. Like {name} was the only person in the whole world.",
        ]),

        # --- PAGE 10: Illustration — Jesus kneels to child ---
        ("image", img("scene-04.jpg")),

        # --- PAGE 11: Text — Spread 4 ---
        ("text", [
            f"He put His hand on {name}\u2019s shoulder, and when He smiled, it felt like the sun had come out twice.",
            f"{name} didn\u2019t know His name yet. But {he} knew \u2014 the way you know your own mother\u2019s voice in a crowded room \u2014 that this man was good. All the way through.",
            f"\u201cWhat\u2019s your name?\u201d {name} whispered.",
            "The man smiled. \u201cJesus,\u201d He said \u2014 like it was a gift He\u2019d been waiting to give.",
        ]),

        # --- PAGE 12: Illustration — Last Supper ---
        ("image", img("scene-05.jpg")),

        # --- PAGE 13: Text — Spread 5 ---
        ("text", [
            f"The days that followed were like a dream {name} didn\u2019t want to wake from. {He} stayed close to Jesus \u2014 watching Him teach, watching Him heal, watching the way people\u2019s faces changed when He spoke to them.",
            f"Then one evening, in a quiet room above a busy street, Jesus gathered His closest friends for a special dinner. And He lifted {name} right onto His lap \u2014 like it was the most natural thing in the world. Like there was always room.",
            "He took bread, gave thanks, and broke it. Then He passed it to His friends gently, the way you hand someone something precious.",
            "\u201cTake and eat,\u201d He said. \u201cThis is my body. Do this in remembrance of me.\u201d",
            f"His voice was steady. But His eyes looked like they were holding something heavy \u2014 a sadness {name} was too young to understand and too close to miss.",
            f"{name} leaned into Him a little tighter. Jesus held {him} a little closer.",
        ]),

        # --- PAGE 14: Illustration — Gethsemane ---
        ("image", img("scene-06.jpg")),

        # --- PAGE 15: Text — Spread 6 ---
        ("text", [
            "Later, in a garden full of old olive trees that twisted toward the sky like hands reaching for God, Jesus knelt down and prayed.",
            f"{name} could hear His voice breaking \u2014 the way ice cracks on a pond in spring. Slowly. Then all at once.",
            "And then came the torches.",
            "Angry voices. Soldiers with swords. Men who had already decided what was going to happen before they even arrived.",
            f"{name} hid behind a tree and pressed both hands against {his} mouth so no one would hear {him} breathing.",
        ]),

        # --- PAGE 16: Illustration — Jesus taken away ---
        ("image", img("scene-07.jpg")),

        # --- PAGE 17: Text — Spread 7 ---
        ("text", [
            "They took Him away.",
            f"The same hands that had broken bread, the same hands that had rested on {name}\u2019s shoulder \u2014 they were bound now. And He didn\u2019t fight it. He just walked.",
            f"{name} followed through the dark streets, past the walls still warm from the afternoon sun, until {he} couldn\u2019t follow anymore.",
            f"{He} pressed {himself} against the cold stone and reached out one hand as if {he} could pull Him back. The palm branch was still in {his} fingers \u2014 wilted now, brown and limp, like it had died right along with everything else.",
            f"\u201cWait,\u201d {name} whispered. But no one heard.",
        ]),

        # --- PAGE 18: Illustration — Mary holds the child ---
        ("image", img("scene-08.jpg")),

        # --- PAGE 19: Text — Spread 8 ---
        ("text", [
            f"They hurt Jesus. {name} didn\u2019t understand why. He hadn\u2019t done anything wrong \u2014 He had only ever been gentle, and good, and full of love.",
            "But they hurt Him anyway. And then He was gone.",
            f"{name} stood alone on a hillside where no child should have to stand, and {he} didn\u2019t know what to do with the ache inside {his} chest.",
            f"That\u2019s when Mary found {him}.",
            f"She was Jesus\u2019 mother. Her eyes were kind, and sad, and full of something that looked like it might be the oldest love in the world. She didn\u2019t ask {name}\u2019s name. She just knelt down and pulled {him} close \u2014 so close {he} could hear her heartbeat, and it sounded like it was breaking.",
            f"{name} buried {his} face in her shoulder and held on.",
            "Because sometimes love doesn\u2019t need words. Sometimes love is just holding someone while the sky goes dark.",
        ]),

        # --- PAGE 20: Illustration — Holy Saturday / child alone ---
        ("image", img("scene-09.jpg")),

        # --- PAGE 21: Text — Spread 9 ---
        ("text", [
            f"The next day, {name} sat very still.",
            "The streets were empty. Doors were shut. Even the birds were quiet, as if the whole world was holding its breath, waiting for something it couldn\u2019t name.",
            f"The palm branch lay on the ground beside {him} \u2014 brown, curled, lifeless. {He} didn\u2019t pick it up.",
            f"\u201cIt wasn\u2019t supposed to end like this,\u201d {name} whispered to no one.",
            "Jesus was gone. Really gone. And the whole world felt emptier because of it.",
            f"And {name} wondered if joy was something that could die and never come back.",
        ]),

        # --- PAGE 22: Illustration — Easter dawn ---
        ("image", img("scene-10.jpg")),

        # --- PAGE 23: Text — Spread 10 ---
        ("text", [
            f"But on the third morning, so early the stars hadn\u2019t finished their shift, {name} woke to something {he} did not expect.",
            "A light. Not like sunrise \u2014 bigger than that, warmer than that, like the whole sky was trying to smile.",
            f"A bird sang one note from the archway above {him}. Then another. Then the whole world seemed to remember what music was.",
            f"{name} stood up. {His} heart was beating fast \u2014 not with fear this time, but with something {he}\u2019d forgotten the name of.",
            "Hope.",
        ]),

        # --- PAGE 24: Illustration — Running to empty tomb ---
        ("image", img("scene-11.jpg")),

        # --- PAGE 25: Text — Spread 11 ---
        ("text", [
            f"{name} ran.",
            f"Faster than {he} had ever run before \u2014 past the stone steps, past the shuttered windows, past the place where the palm branch had been lying on the ground (it was gone now, and so was the sadness that had been sitting on top of it).",
            f"{He} ran until {he} reached a garden that hadn\u2019t looked like this before. Flowers that weren\u2019t there yesterday were blooming everywhere, as if the ground itself had heard the news and couldn\u2019t contain its joy.",
            "And the tomb \u2014 the one they had sealed shut, the one that was supposed to be the end of the story \u2014",
            "It was open. The stone was rolled away. And it was full of light.",
        ]),

        # --- PAGE 26: Illustration — Jesus lifts child in garden ---
        ("image", img("scene-12.jpg")),

        # --- PAGE 27: Text — Spread 12 (THE FINALE) ---
        ("finale", [
            "And there \u2014 standing in the morning light like He had all the time in the world, like death was just a place He had visited and decided not to stay \u2014",
            "was Jesus.",
            f"Alive. Smiling. Real as the ground beneath {name}\u2019s feet.",
            f"{He} opened His arms, and {name} didn\u2019t walk. {He} ran. {He} crashed into Him the way waves crash into the shore \u2014 not carefully, not gently, but with everything {he} had.",
            f"And Jesus picked {him} up and held {him} high and laughed \u2014 the kind of laugh that makes flowers bloom and birds take flight and broken things become whole.",
            "",
            f"\u201cSee, {name}?\nI did this for you.\nBecause I love you.\nI have always loved you.\nAnd nothing \u2014 not nails, not a tomb, not even death itself \u2014\ncould keep me from coming back to you.\u201d",
            f"And {name} held on tight and whispered back:\n\u201cThank You Jesus. I love you too!\u201d",
        ], img("scene-12.jpg")),

        # --- PAGE 28: Promo ---
        ("promo", [
            "More adventures coming soon\u2026",
            "",
            "THE NAMED STORY",
            "www.thenamedstory.com",
        ]),

        # --- PAGE 29: Copyright ---
        ("copyright", [
            "\u201cI have called you by name. You are mine.\u201d",
            "ISAIAH 43:1",
            "",
            "\u00a9 2026 The Named Story. All rights reserved.",
        ]),

        # --- PAGE 30: Blank (inside back) ---
        ("blank",),
    ]
    return pages


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_book(name, gifter, variant, output):
    """Generate the complete personalized book PDF."""
    register_fonts()
    pages = build_book(name, gifter, variant)
    c = canvas.Canvas(output, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{name} and the First Easter")
    c.setAuthor("The Named Story")

    for entry in pages:
        ptype = entry[0]
        if ptype == "blank":
            pg_blank(c)
        elif ptype == "image":
            pg_image(c, entry[1])
        elif ptype == "cover":
            pg_cover(c, entry[2], entry[1])
        elif ptype == "dedication":
            pg_dedication(c, entry[1])
        elif ptype == "text":
            pg_text(c, entry[1])
        elif ptype == "finale":
            pg_finale(c, entry[1], entry[2])
        elif ptype == "promo":
            pg_promo(c, entry[1])
        elif ptype == "copyright":
            pg_copyright(c, entry[1])
        c.showPage()

    c.save()
    kb = os.path.getsize(output) / 1024
    print(f"\n  \u2705 Book generated: {output}")
    print(f"     {len(pages)} pages | {PAGE_W/inch:.0f}\u00d7{PAGE_H/inch:.0f}\" | {name} | {variant} | {kb:.0f} KB\n")
    return output


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate a personalized Named Story Easter book")
    ap.add_argument("--name", required=True, help="Child's first name")
    ap.add_argument("--gifter", default="", help="Gift from (e.g. 'Grandma & Grandpa')")
    ap.add_argument("--variant", required=True, help="Character variant (e.g. 'boy-dark-brown')")
    ap.add_argument("--output", default=None, help="Output PDF filename")
    a = ap.parse_args()
    if not a.output:
        a.output = f"{a.name.lower().replace(' ', '-')}-easter-book.pdf"
    generate_book(a.name, a.gifter, a.variant, a.output)
