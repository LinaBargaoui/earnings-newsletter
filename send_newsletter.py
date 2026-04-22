"""
Daily Earnings Newsletter Sender
Scrapes vitalknowledge.net, formats content, sends to email list.
"""

import os
import re
import json
import smtplib
import hashlib
import requests
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
# CONFIGURATION — Edit these values
# ──────────────────────────────────────────────
RECIPIENTS = [
    "subscriber1@example.com",
    "subscriber2@example.com",
    # Add as many emails as you like
]

SENDER_NAME    = "WLC Market Recap"
SENDER_EMAIL   = os.environ["GMAIL_ADDRESS"]    # set in GitHub Secrets
GMAIL_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]  # set in GitHub Secrets

SOURCE_URL = "https://vitalknowledge.net/?category=earnings"
SENT_LOG   = "sent_articles.json"   # tracks what was already sent

# ──────────────────────────────────────────────
# STEP 1 — Scrape the latest article
# ──────────────────────────────────────────────
def get_latest_article():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsletterBot/1.0)"}
    resp = requests.get(SOURCE_URL, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try common blog post selectors (adjust if site changes)
    selectors = [
        "article",
        ".post",
        ".entry",
        ".blog-post",
        "[class*='post']",
        "main .content",
    ]

    article_el = None
    for sel in selectors:
        found = soup.select(sel)
        if found:
            article_el = found[0]
            break

    if not article_el:
        # Fallback: grab the biggest block of text on the page
        article_el = soup.find("main") or soup.find("body")

    # Extract title
    title_el = (
        article_el.find(["h1", "h2"])
        or soup.find("h1")
        or soup.find("title")
    )
    title = title_el.get_text(strip=True) if title_el else "Market Earnings Recap"

    # Extract date
    date_el = article_el.find(["time", "[datetime]", ".date", ".published"])
    pub_date = None
    if date_el:
        pub_date = date_el.get("datetime") or date_el.get_text(strip=True)
    if not pub_date:
        pub_date = datetime.now().strftime("%B %d, %Y")

    # Extract paragraphs (skip nav/footer noise)
    paragraphs = []
    for el in article_el.find_all(["p", "li", "h2", "h3", "h4"]):
        text = el.get_text(separator=" ", strip=True)
        if len(text) > 40:   # ignore tiny/nav items
            paragraphs.append((el.name, text))

    content_hash = hashlib.md5(
        "".join(t for _, t in paragraphs[:5]).encode()
    ).hexdigest()

    return {
        "title":   title,
        "date":    pub_date,
        "paras":   paragraphs,
        "hash":    content_hash,
        "url":     SOURCE_URL,
    }


# ──────────────────────────────────────────────
# STEP 2 — Duplicate check
# ──────────────────────────────────────────────
def already_sent(article_hash: str) -> bool:
    if not os.path.exists(SENT_LOG):
        return False
    with open(SENT_LOG) as f:
        sent = json.load(f)
    return article_hash in sent.get("hashes", [])


def mark_sent(article_hash: str):
    sent = {"hashes": []}
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG) as f:
            sent = json.load(f)
    sent["hashes"] = [article_hash] + sent["hashes"][:49]   # keep last 50
    with open(SENT_LOG, "w") as f:
        json.dump(sent, f, indent=2)


# ──────────────────────────────────────────────
# STEP 3 — Build the HTML email
# ──────────────────────────────────────────────
def build_html_email(article: dict) -> str:
    today = datetime.now().strftime("%B %d, %Y")

    # Build content rows
    rows_html = ""
    for tag, text in article["paras"]:
        if tag in ("h2", "h3", "h4"):
            rows_html += f"""
            <tr>
              <td style="padding:16px 32px 4px 32px;
                         font-family:Calibri,Arial,sans-serif;
                         font-size:15px;font-weight:bold;
                         color:#333333;">
                {text}
              </td>
            </tr>"""
        elif tag == "li":
            rows_html += f"""
            <tr>
              <td style="padding:2px 32px 2px 48px;
                         font-family:Calibri,Arial,sans-serif;
                         font-size:14px;color:#444444;">
                &bull;&nbsp;{text}
              </td>
            </tr>"""
        else:
            rows_html += f"""
            <tr>
              <td style="padding:6px 32px;
                         font-family:Calibri,Arial,sans-serif;
                         font-size:14px;color:#444444;
                         line-height:1.6;">
                {text}
              </td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{article['title']}</title></head>
<body style="margin:0;padding:0;background:#f0f0f0;">
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f0f0f0;padding:24px 0;">
  <tr><td align="center">
    <table width="660" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:6px;
                  border:1px solid #dddddd;overflow:hidden;">

      <!-- Header -->
      <tr>
        <td style="background:#1a1a1a;padding:20px 32px;">
          <p style="margin:0;font-family:Calibri,Arial,sans-serif;
                    font-size:11px;color:#888888;letter-spacing:1px;
                    text-transform:uppercase;">WLC Limited Distribution</p>
          <p style="margin:4px 0 0;font-family:Calibri,Arial,sans-serif;
                    font-size:20px;font-weight:bold;color:#ffffff;">
            Market Earnings Recap &mdash; {today}
          </p>
        </td>
      </tr>

      <!-- Article title -->
      <tr>
        <td style="background:#f7f7f7;padding:14px 32px;
                   border-bottom:1px solid #e0e0e0;">
          <p style="margin:0;font-family:Calibri,Arial,sans-serif;
                    font-size:13px;color:#999999;">
            Source: <a href="{article['url']}" style="color:#999999;">
              vitalknowledge.net
            </a>
            &nbsp;&nbsp;|&nbsp;&nbsp;Published: {article['date']}
          </p>
        </td>
      </tr>

      <!-- Body content -->
      {rows_html}

      <!-- Footer -->
      <tr>
        <td style="border-top:1px solid #eeeeee;
                   padding:20px 32px;background:#fafafa;">
          <p style="margin:0;font-family:Calibri,Arial,sans-serif;
                    font-size:11px;color:#bbbbbb;text-align:center;">
            WLC Market Recap &bull; Automated Daily Distribution<br>
            Content sourced from
            <a href="{article['url']}" style="color:#bbbbbb;">
              vitalknowledge.net
            </a>
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""
    return html


# ──────────────────────────────────────────────
# STEP 4 — Send via Gmail SMTP
# ──────────────────────────────────────────────
def send_email(html_body: str, subject: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

    print(f"✅ Sent to {len(RECIPIENTS)} recipient(s).")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("📰 Fetching latest article…")
    article = get_latest_article()
    print(f"   Title : {article['title']}")
    print(f"   Hash  : {article['hash']}")

    if already_sent(article["hash"]):
        print("⏭️  Already sent — no new content today.")
        return

    print("🎨 Building email…")
    html  = build_html_email(article)
    today = datetime.now().strftime("%B %d, %Y")
    subject = f"Market Earnings Recap — {today}"

    print("📬 Sending…")
    send_email(html, subject)
    mark_sent(article["hash"])
    print("✅ Done.")


if __name__ == "__main__":
    main()
