"""Daily digest: new postings, postings closing within 7 days, failed sources.

Delivery: Gmail SMTP (GMAIL_USER, GMAIL_APP_PASSWORD, DIGEST_TO) and/or Telegram (TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID). The digest is always written to out/digest.html and out/digest.txt as well.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .. import config, http
from ..store import Store
from . import data


def build(store: Store, dashboard_url: str = "") -> dict:
    today = dt.date.today()
    posts = [p for p in data.postings(store, include_removed=False) if p.get("verified") == 1]
    new = [p for p in posts if p["first_seen"] == today.isoformat() and p["relevance"] == "keep"]
    new_maybe = [p for p in posts if p["first_seen"] == today.isoformat() and p["relevance"] == "maybe"]
    closing = [p for p in posts if p["display_status"] == "Closing soon"]
    failed = [h for h in data.source_health(store) if not h["health"].startswith("OK")]
    return {"date": today.isoformat(), "new": new, "new_maybe": new_maybe, "closing": closing, "failed": failed,
            "dashboard_url": dashboard_url}


def _line(p):
    return (f"[{p['score']}] {p['company']} – {p['title']} | {p['location']} | {p['pay'] or 'pay n/a'} | "
            f"{p['languages'] or 'languages n/a'}\n    {p['url']}")


def to_text(d: dict) -> str:
    out = [f"Job Radar – {d['date']}", ""]
    out.append(f"NEW POSTINGS ({len(d['new'])})")
    out += [_line(p) for p in d["new"]] or ["  none today"]
    if d["new_maybe"]:
        out += ["", f"NEW 'MAYBE' POSTINGS ({len(d['new_maybe'])})"] + [_line(p) for p in d["new_maybe"][:15]]
    out += ["", f"CLOSING WITHIN 7 DAYS ({len(d['closing'])})"]
    out += [_line(p) + f"  (deadline {p['deadline']})" for p in d["closing"]] or ["  none"]
    out += ["", f"SOURCES WITH PROBLEMS ({len(d['failed'])})"]
    out += [f"  {h['name']} ({h['adapter']}): {h['health']} {h['error']}" for h in d["failed"]] or ["  none"]
    if d["dashboard_url"]:
        out += ["", f"Dashboard: {d['dashboard_url']}"]
    return "\n".join(out)


def to_html(d: dict) -> str:
    e = html.escape

    def rows(ps, extra=False):
        if not ps:
            return "<p style='color:#666'>None.</p>"
        tr = "".join(
            f"<tr><td style='font-weight:700'>{p['score']}</td><td>{e(p['company'])}</td><td>{e(p['title'])}</td>"
            f"<td>{e(p['location'])}</td><td>{e(p['pay'])}</td><td>{e(p['languages'])}</td>"
            + (f"<td>{e(p['deadline'])}</td>" if extra else "")
            + f"<td><a href='{e(p['url'])}'>official link</a></td></tr>" for p in ps)
        hd = "<tr><th>Score</th><th>Company</th><th>Role</th><th>City</th><th>Pay</th><th>Languages</th>" + \
             ("<th>Deadline</th>" if extra else "") + "<th></th></tr>"
        return f"<table cellpadding='5' style='border-collapse:collapse;font-size:13px' border='1'>{hd}{tr}</table>"
    fail = "".join(f"<li><b>{e(h['name'])}</b> ({e(h['adapter'])}): {e(h['health'])} {e(h['error'])}</li>" for h in d["failed"])
    link = f"<p><a href='{e(d['dashboard_url'])}'>Open the dashboard</a></p>" if d["dashboard_url"] else ""
    return (f"<html><body style='font-family:Arial,sans-serif'><h2>Job Radar – {e(d['date'])}</h2>{link}"
            f"<h3>New postings ({len(d['new'])})</h3>{rows(d['new'])}"
            + (f"<h3>New 'maybe' postings ({len(d['new_maybe'])})</h3>{rows(d['new_maybe'][:15])}" if d["new_maybe"] else "")
            + f"<h3>Closing within 7 days ({len(d['closing'])})</h3>{rows(d['closing'], True)}"
            f"<h3>Sources with problems ({len(d['failed'])})</h3><ul>{fail or '<li>none</li>'}</ul></body></html>")


def send(d: dict, log=print) -> list[str]:
    sent = []
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUT_DIR / "digest.txt").write_text(to_text(d), encoding="utf-8")
    (config.OUT_DIR / "digest.html").write_text(to_html(d), encoding="utf-8")
    subject = f"Job Radar {d['date']}: {len(d['new'])} new, {len(d['closing'])} closing soon" + \
              (f", {len(d['failed'])} source issues" if d["failed"] else "")
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if user and pw:
        to = os.environ.get("DIGEST_TO") or user
        msg = MIMEMultipart("alternative")
        msg["Subject"], msg["From"], msg["To"] = subject, user, to
        msg.attach(MIMEText(to_text(d), "plain", "utf-8"))
        msg.attach(MIMEText(to_html(d), "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
            s.login(user, pw)
            s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
        sent.append("email")
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        text = to_text(d)
        for i in range(0, len(text), 3900):
            r = http.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text[i:i + 3900], "disable_web_page_preview": True})
            r.raise_for_status()
        sent.append("telegram")
    log(f"Digest: {subject} → {', '.join(sent) or 'written to out/ only (no email/Telegram configured)'}")
    return sent
