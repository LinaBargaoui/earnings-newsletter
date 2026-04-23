"""
WLC Market Newsletter Sender
- Daily Brief:      Mon–Fri at 6:00 UTC (= 8:00 AM UTC+2)
                    Contains ALL Vital Knowledge posts from the previous day
- Weekly Recap:     Friday at 16:00 UTC (= 6:00 PM UTC+2)
                    Contains the week recap post from Vital Knowledge
- Week Prep:        Sunday at 06:00 UTC (= 8:00 AM UTC+2)
                    Contains Sunday's "Getting Ready for the Week" post
"""

import os, re, json, hashlib, smtplib, sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────
RECIPIENTS = [
    "subscriber1@example.com",
    "subscriber2@example.com",
]

SENDER_NAME    = "WLC Market Recap"
SENDER_EMAIL   = os.environ["GMAIL_ADDRESS"]
GMAIL_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

SOURCE_URL  = "https://vitalknowledge.net/?category=earnings"
SENT_LOG    = "sent_articles.json"

# Newsletter type is passed as CLI arg: daily | weekly | weekprep
NEWSLETTER_TYPE = sys.argv[1] if len(sys.argv) > 1 else "daily"

# ── COLOR CONSTANTS ───────────────────────────────────────────────────────────
C_GREEN    = "#1A7A50"
C_RED      = "#C94444"
C_GRAY     = "#888888"
C_BODY     = "#333333"
C_SUMMARY  = "#444444"
C_SENT     = "#999999"
C_HEAD_BG  = "#1a1a1a"
C_SECTION  = "#222222"

# ── KNOWN TICKERS (bold these always) ────────────────────────────────────────
KNOWN_TICKERS = set("""
JPM BAC C WFC GS MS BK SCHW USB PNC STT TFC FITB RF ALLY MTB CFG KEY HBAN ZION
WTFC WAL EWBC ARES BX KKR APO BLK IVZ OWL CBOE CME ICE NDAQ IBKR HOOD COIN
CB TRV PRU MET AIG AJG AON BRO HIG RNR ACGL ERIE PGR
LVMH TPR RL NKE PVH LULU DECK PEP KO BUD
HLT MAR IHG CCL RCL NCLH AAL DAL UAL LUV ALK
MCD SBUX DPZ YUM CMG PZZA WMT TGT COST DG DLTR ULTA HAS WSM
NFLX DIS WBD PARA CZR LVS WYNN MGM
ASML INTC TSM LRCX AVGO NVDA AMD QCOM AMAT KLAC MRVL MU ON STX WDC ADI TXN
NXPI MPWR TEL GLW COHR JBL EPAM TER
NOW SAP ADBE CRM SNOW WDAY HUBS MDB DDOG FTNT PANW ZS CRWD ORCL GTLB AKAM
TEAM CDNS SNPS IBM MSFT
GOOGL META AMZN BIDU SNAP PINS SPOT UBER LYFT PLTR AAPL
BA LMT RTX NOC GD HII LHX TXT LDOS SAIC
GE GEV HON EMR ETN PH IR ROK ITW TT WAB OTIS CARR SWK SNA DOV CMI GNRC URI HUBB
MMM HWM CAT PCAR VMC MLM DE
UPS FDX XPO SAIA ODFL EXPD CHRW UNP CSX NSC JBHT KNX WERN
F GM TSLA ALV APTV MGA LEA BWA PATK LCII
COP APA OXY DVN MRO CTRA MPC PSX VLO XOM CVX SLB HAL BKR
DOW LYB ALB CF CE EMN PPG LIN APD AA NEM FCX NUE STLD CLF RS
JNJ LLY PFE MRK ABBV AMGN GILD BMY REGN BIIB UNH CVS CI HUM ELV MOH CNC
TMO DHR BSX MDT ABT SYK ISRG BAX MTD IDXX
PLD EQR AVB CCI AMT EQIX DLR SLG
NI ATO CEG CNP DUK EIX EXC SRE NEE SO PCG VST NRG
MRVL APP GDDY TTD WDAY CLF BRC USAR SILA RYAM BLD QXO
""".split())

KNOWN_COMPANIES = [
    "Apple","Microsoft","Tesla","Google","Meta","Nvidia","Intel","Broadcom",
    "Adobe","Salesforce","Oracle","Netflix","Disney","Airbnb","Amazon","Anthropic",
    "Berkshire","Eli Lilly","Honeywell","Shell","BP","Blue Owl","Brown-Forman",
    "Pernod Ricard","Heineken","LVMH","Hermes","Kering","Moncler","TopBuild",
    "McKesson","Brady Corp","Caesars","Rayonier","Spirit Airlines","Jersey Mike",
    "Commerzbank","Unicredit","Stanley Black","Decker","Kelonia",
]

KNOWN_PEOPLE = [
    "Tim Cook","Mark Zuckerberg","Jamie Dimon","Jensen Huang","Elon Musk",
    "Jeff Bezos","Sam Altman","Dario Amodei","Andy Jassy","Greg Abel",
    "Todd Combs","Marc Benioff","Charlie Scharf","Kevin Warsh","Jerome Powell",
    "John Ternus","Tilman Fertitta",
]

# Never bold these even if uppercase
NEVER_BOLD = {
    "CEO","CTO","COO","CFO","CRO","EVP","SVP","VP","MD","GM","CMO",
    "GDP","EPS","NIM","BPS","YOY","YTD","QOQ","FY","US","UK","EU","FX",
    "SPX","DOW","NASDAQ","FED","DOJ","DOD","SEC","FBI","IRS","NYSE","FOMC",
    "Q1","Q2","Q3","Q4","IPO","RIF","EST","MOU","AWS","TPU","IRGC",
    "ET","AM","PM","TV","AI","M&A","PE","VC","LBO",
}

# ── BOLD HELPER ───────────────────────────────────────────────────────────────
def bold_tickers(text: str) -> str:
    """Wrap known tickers, company names, and people names in <b> tags."""
    # Tickers: 2-5 uppercase letters, not in NEVER_BOLD
    def replace_ticker(m):
        word = m.group(0)
        if word in NEVER_BOLD:
            return word
        if word in KNOWN_TICKERS:
            return f'<b>{word}</b>'
        return word

    text = re.sub(r'\b[A-Z]{2,5}\b', replace_ticker, text)

    # Company names
    for name in sorted(KNOWN_COMPANIES, key=len, reverse=True):
        text = text.replace(name, f'<b>{name}</b>')

    # People names
    for name in sorted(KNOWN_PEOPLE, key=len, reverse=True):
        text = text.replace(name, f'<b>{name}</b>')

    return text


def fmt_perf(text: str) -> str:
    """Color +X.X% green and -X.X% red, replace — with -."""
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(
        r'(\+[\d.]+%)',
        rf'<span style="color:{C_GREEN};font-weight:bold">\1</span>',
        text
    )
    text = re.sub(
        r'(-[\d.]+%)',
        rf'<span style="color:{C_RED};font-weight:bold">\1</span>',
        text
    )
    # [Beat] / [Miss] / [In line]
    text = re.sub(r'\[Beat\]',    f'<span style="color:{C_GREEN};font-weight:bold">[Beat]</span>', text)
    text = re.sub(r'\[Miss\]',    f'<span style="color:{C_RED};font-weight:bold">[Miss]</span>', text)
    text = re.sub(r'\[In line\]', f'<span style="color:{C_GRAY};font-weight:bold">[In line]</span>', text)
    # Source in (parens) → gray
    text = re.sub(r'\(([^)]{2,40})\)', rf'<span style="color:{C_SENT}">(\1)</span>', text)
    return text


def process(text: str) -> str:
    return fmt_perf(bold_tickers(text))


# ── SCRAPER ───────────────────────────────────────────────────────────────────
def fetch_articles(target_date: datetime) -> list[dict]:
    """
    Scrape vitalknowledge.net and return articles published on target_date.
    target_date is a date in local time (UTC+2).
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WLCNewsletterBot/2.0)"}
    articles = []

    # Try paginated fetch (page 1 and 2 to be safe)
    for page in range(1, 4):
        url = SOURCE_URL if page == 1 else f"{SOURCE_URL}&paged={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=25)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Warning: could not fetch page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find all article blocks
        posts = soup.find_all(["article", "div"],
                               class_=re.compile(r'post|entry|article', re.I))

        if not posts:
            # fallback: any <article> tag
            posts = soup.find_all("article")

        found_any = False
        for post in posts:
            # --- Title ---
            title_el = post.find(["h1","h2","h3"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            # --- URL ---
            link_el = title_el.find("a") or post.find("a")
            post_url = link_el["href"] if link_el and link_el.get("href") else SOURCE_URL

            # --- Date ---
            date_el = post.find("time") or post.find(class_=re.compile(r'date|time|publish', re.I))
            pub_date = None
            if date_el:
                dt_str = date_el.get("datetime") or date_el.get_text(strip=True)
                for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%B %d, %Y",
                             "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"]:
                    try:
                        pub_date = datetime.strptime(dt_str[:19], fmt[:len(dt_str[:19])])
                        break
                    except Exception:
                        pass

            # If we can't parse date, assume it's recent and include it
            if pub_date is None:
                pub_date = target_date

            # Normalize to date only for comparison
            pub_day = pub_date.date() if hasattr(pub_date, 'date') else target_date.date()
            target_day = target_date.date()

            if pub_day < target_day:
                # Articles are chronological; stop if we've gone past target
                break

            if pub_day == target_day:
                found_any = True
                # --- Body ---
                body_el = post.find(class_=re.compile(r'content|body|excerpt', re.I)) or post
                paragraphs = []
                for el in body_el.find_all(["p","li","h2","h3","h4","blockquote"]):
                    t = el.get_text(separator=" ", strip=True)
                    if len(t) > 30:
                        paragraphs.append((el.name, t))

                content_hash = hashlib.md5(title.encode()).hexdigest()

                articles.append({
                    "title":    title,
                    "url":      post_url,
                    "date":     pub_date,
                    "paras":    paragraphs,
                    "hash":     content_hash,
                })

        if not found_any and page > 1:
            break

    # De-duplicate by hash
    seen = set()
    unique = []
    for a in articles:
        if a["hash"] not in seen:
            seen.add(a["hash"])
            unique.append(a)

    return unique


# ── DUPLICATE LOG ─────────────────────────────────────────────────────────────
def already_sent(batch_key: str) -> bool:
    if not os.path.exists(SENT_LOG):
        return False
    with open(SENT_LOG) as f:
        sent = json.load(f)
    return batch_key in sent.get("keys", [])


def mark_sent(batch_key: str):
    sent = {"keys": []}
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG) as f:
            sent = json.load(f)
    sent["keys"] = [batch_key] + sent.get("keys", [])[:99]
    with open(SENT_LOG, "w") as f:
        json.dump(sent, f, indent=2)


# ── HTML BUILDER ──────────────────────────────────────────────────────────────
RESPONSIVE_STYLE = """
<style>
  /* ── Reset ── */
  body, table, td { margin:0; padding:0; }
  img { border:0; display:block; }

  /* ── Desktop base ── */
  .wrapper   { background:#f0f0f0; padding:24px 0; }
  .container { width:660px; margin:0 auto; background:#ffffff;
               border-radius:6px; border:1px solid #dddddd; overflow:hidden; }
  .header    { background:#1a1a1a; padding:20px 32px; }
  .header-label { font-family:Calibri,Arial,sans-serif; font-size:11px;
                  color:#888888; letter-spacing:1px; text-transform:uppercase; margin:0; }
  .header-title { font-family:Calibri,Arial,sans-serif; font-size:20px;
                  font-weight:bold; color:#ffffff; margin:4px 0 0; }
  .market-bar  { background:#f7f7f7; padding:12px 32px;
                 border-bottom:1px solid #e0e0e0; }
  .market-bar p { font-family:Calibri,Arial,sans-serif; font-size:12px;
                  color:#555555; margin:0; }
  .section-header { background:#f0f0f0; padding:10px 32px 6px;
                    border-top:2px solid #1a1a1a; }
  .section-title  { font-family:Calibri,Arial,sans-serif; font-size:13px;
                    font-weight:bold; color:#222222; margin:0;
                    text-transform:uppercase; letter-spacing:0.5px; }
  .section-sentiment { font-family:Calibri,Arial,sans-serif; font-size:11px;
                       color:#555555; margin:2px 0 0; }
  .summary   { padding:10px 32px 4px; font-family:Calibri,Arial,sans-serif;
               font-size:13px; color:#444444; line-height:1.6; }
  .sub-label { padding:8px 32px 2px; font-family:Calibri,Arial,sans-serif;
               font-size:11px; font-weight:bold; color:#333333;
               text-transform:uppercase; letter-spacing:0.8px; }
  .bullet    { padding:2px 32px 2px 44px; font-family:Calibri,Arial,sans-serif;
               font-size:13px; color:#444444; line-height:1.5; }
  .article-divider { border:none; border-top:1px dashed #dddddd;
                     margin:16px 32px; }
  .footer    { background:#fafafa; border-top:1px solid #eeeeee;
               padding:16px 32px; text-align:center; }
  .footer p  { font-family:Calibri,Arial,sans-serif; font-size:11px;
               color:#bbbbbb; margin:0; }

  /* ── Mobile overrides (<600px) ── */
  @media only screen and (max-width:620px) {
    .wrapper   { padding:0 !important; }
    .container { width:100% !important; border-radius:0 !important;
                 border-left:none !important; border-right:none !important; }
    .header    { padding:16px 18px !important; }
    .header-label { font-size:10px !important; }
    .header-title { font-size:18px !important; }
    .market-bar  { padding:10px 18px !important; }
    .market-bar p { font-size:13px !important; }
    .section-header { padding:10px 18px 6px !important; }
    .section-title  { font-size:14px !important; }
    .section-sentiment { font-size:12px !important; }
    .summary   { padding:10px 18px 4px !important; font-size:14px !important; }
    .sub-label { padding:8px 18px 2px !important; font-size:12px !important; }
    .bullet    { padding:3px 18px 3px 30px !important; font-size:14px !important;
                 line-height:1.6 !important; }
    .article-divider { margin:12px 18px !important; }
    .footer    { padding:14px 18px !important; }
    .footer p  { font-size:12px !important; }
  }
</style>
"""


def sentiment_color(sentiment: str) -> str:
    s = sentiment.lower()
    if any(w in s for w in ["positive","bullish","constructive","outperform"]):
        return C_GREEN
    if any(w in s for w in ["negative","bearish","underperform","weak"]):
        return C_RED
    if "mixed" in s or "neutral" in s:
        return C_GRAY
    return C_GRAY


def parse_sections(paragraphs: list) -> str:
    """Convert raw paragraph list into formatted section HTML."""
    html = ""
    current_section = None
    current_sentiment = ""

    SECTION_ORDER = [
        "MARKET VIEW","MACRO","WASHINGTON","IRAN","MIDDLE EAST",
        "FINANCIALS","INSURANCE","CONSUMER","LUXURY","HEALTH CARE",
        "DEFENSE","AEROSPACE","SEMIS","HARDWARE","SOFTWARE","AI","PLATFORMS",
        "TELECOM","MEDIA","ENERGY","MATERIALS","INDUSTRIALS","TRANSPORT",
        "AUTOS","REAL ESTATE","UTILITIES","M&A","CORPORATE","CALENDAR",
    ]

    SUB_LABELS = {"bull case","bear case","earnings print","coming up",
                  "what outperformed","what underperformed","key developments"}

    for tag, text in paragraphs:
        # Detect section header (*** prefix or all-caps short line)
        is_section = text.startswith("***") or (
            tag in ("h2","h3","h4") and len(text) < 80
        )

        if is_section:
            clean = text.lstrip("*").strip()
            parts = [p.strip() for p in clean.split("|")]
            sec_name   = parts[0].upper()
            sentiment  = parts[1] if len(parts) > 1 else ""
            key_info   = parts[2] if len(parts) > 2 else ""

            s_color = sentiment_color(sentiment)
            current_section   = sec_name
            current_sentiment = sentiment

            sentiment_html = ""
            if sentiment:
                sentiment_html = (
                    f'<p class="section-sentiment">'
                    f'<span style="color:{s_color};font-weight:bold">{sentiment}</span>'
                    + (f' <span style="color:{C_SENT}">| {key_info}</span>' if key_info else "")
                    + "</p>"
                )

            html += f"""
<div class="section-header">
  <p class="section-title">*** {sec_name}</p>
  {sentiment_html}
</div>"""
            continue

        # Sub-labels (Bull Case, Bear Case, etc.)
        if text.lower().rstrip(":") in SUB_LABELS or text.lower().startswith(("bull","bear","earnings print","coming up")):
            label = text.rstrip(":")
            html += f'<p class="sub-label">{label}</p>'
            continue

        # Bullet points
        if tag == "li" or text.startswith("-") or text.startswith("•"):
            clean = text.lstrip("-•").strip()
            html += f'<p class="bullet">- {process(clean)}</p>'
            continue

        # Normal paragraph / summary
        html += f'<p class="summary">{process(text)}</p>'

    return html


def build_article_html(article: dict, show_title: bool = True) -> str:
    """Build the HTML block for one article."""
    html = ""
    if show_title:
        date_str = ""
        if article.get("date"):
            try:
                date_str = article["date"].strftime("%B %d, %Y")
            except Exception:
                date_str = str(article["date"])

        html += f"""
<div style="padding:14px 32px 6px;background:#f9f9f9;border-bottom:1px solid #eeeeee;">
  <p style="margin:0;font-family:Calibri,Arial,sans-serif;font-size:13px;
            font-weight:bold;color:#222222;">{article['title']}</p>
  <p style="margin:2px 0 0;font-family:Calibri,Arial,sans-serif;font-size:11px;
            color:{C_SENT};">{date_str} &nbsp;|&nbsp;
    <a href="{article['url']}" style="color:{C_SENT};">vitalknowledge.net</a>
  </p>
</div>"""

    html += parse_sections(article["paras"])
    return html


def build_full_email(articles: list, newsletter_type: str, subject_date: str) -> str:
    """Assemble the complete responsive HTML email."""
    today_str = datetime.now(timezone(timedelta(hours=2))).strftime("%B %d, %Y")

    type_labels = {
        "daily":    "Daily Market Brief",
        "weekly":   "Weekly Recap",
        "weekprep": "Getting Ready for the Week",
    }
    label = type_labels.get(newsletter_type, "Market Brief")

    # Articles content
    articles_html = ""
    for i, art in enumerate(articles):
        if i > 0:
            articles_html += '<hr class="article-divider">'
        articles_html += build_article_html(art, show_title=(len(articles) > 1))

    if not articles_html:
        articles_html = f'<p class="summary" style="color:{C_SENT};font-style:italic;">No new content found for this period.</p>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WLC {label} - {subject_date}</title>
{RESPONSIVE_STYLE}
</head>
<body>
<div class="wrapper">
  <div class="container">

    <!-- Header -->
    <div class="header">
      <p class="header-label">WLC Limited Distribution</p>
      <p class="header-title">WLC {label} &mdash; {subject_date}</p>
    </div>

    <!-- Articles -->
    {articles_html}

    <!-- Footer -->
    <div class="footer">
      <p>WLC Market Recap &bull; {label} &bull; {today_str}<br>
         Content sourced from
         <a href="{SOURCE_URL}" style="color:#bbbbbb;">vitalknowledge.net</a>
      </p>
    </div>

  </div>
</div>
</body>
</html>"""
    return html


# ── EMAIL SENDER ──────────────────────────────────────────────────────────────
def send_email(html_body: str, subject: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

    print(f"  Sent to {len(RECIPIENTS)} recipient(s).")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    tz_utc2 = timezone(timedelta(hours=2))
    now_local = datetime.now(tz_utc2)

    print(f"Newsletter type : {NEWSLETTER_TYPE}")
    print(f"Local time UTC+2: {now_local.strftime('%A %B %d, %Y %H:%M')}")

    # Determine which date's articles to fetch
    if NEWSLETTER_TYPE == "daily":
        # Mon–Fri: send previous day's posts at 8 AM UTC+2
        target_date = now_local - timedelta(days=1)
        # If Monday, go back to Friday (skip weekend)
        if now_local.weekday() == 0:
            target_date = now_local - timedelta(days=3)
        subject_date = target_date.strftime("%A, %B %-d")
        subject = f"WLC Daily Brief - {target_date.strftime('%m/%d/%Y')}"

    elif NEWSLETTER_TYPE == "weekly":
        # Friday at 6 PM: week recap (current week's posts or latest recap)
        target_date = now_local
        subject_date = f"Week of {(now_local - timedelta(days=4)).strftime('%B %-d')} - {now_local.strftime('%B %-d, %Y')}"
        subject = f"WLC Weekly Recap - {now_local.strftime('%m/%d/%Y')}"

    elif NEWSLETTER_TYPE == "weekprep":
        # Sunday: prep for the week (same day posts)
        target_date = now_local
        subject_date = f"Week of {(now_local + timedelta(days=1)).strftime('%B %-d, %Y')}"
        subject = f"WLC Getting Ready for the Week - {now_local.strftime('%m/%d/%Y')}"

    else:
        print(f"Unknown newsletter type: {NEWSLETTER_TYPE}")
        sys.exit(1)

    # Batch key for duplicate check
    batch_key = f"{NEWSLETTER_TYPE}_{target_date.strftime('%Y-%m-%d')}"

    if already_sent(batch_key):
        print(f"Already sent [{batch_key}] — skipping.")
        return

    print(f"Fetching articles for: {target_date.strftime('%Y-%m-%d')} …")
    articles = fetch_articles(target_date)
    print(f"  Found {len(articles)} article(s).")

    if not articles:
        print("  No articles found — sending empty notice.")

    print("Building email …")
    html = build_full_email(articles, NEWSLETTER_TYPE, subject_date)

    print("Sending …")
    send_email(html, subject)
    mark_sent(batch_key)
    print("Done.")


if __name__ == "__main__":
    main()
