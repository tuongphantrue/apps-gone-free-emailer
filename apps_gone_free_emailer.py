#!/usr/bin/env python3
"""
apps_gone_free_emailer.py

Daily "iOS apps gone free" digest -> email (runs on GitHub Actions, no local
computer needed). Same generate/send two-phase shape, Gmail-SMTP delivery,
and dedup-via-state-branch trick as gold-price-emailer / house-price-emailer
/ tech-price-mailer / currency-rate-emailer.

WHICH SITE THIS SCRAPES, AND WHY
----------------------------------
A lot of the well-known "apps gone free" trackers people remember are dead:

- AppShopper.com (the original) shut down 2021-06-30.
- iOSnoops.com - active as recently as 2023 - has since shut down too
  ("we have decided to shut down the site... the economics are not there
  anymore" per its own homepage).
- AppAdvice's "Apps Gone Free" daily list stopped being updated in early
  2026 (Apple tightened App Review enforcement on free-to-paid price-flip
  promos). appadvice.com/apps-gone-free is still online but frozen on a
  mid-January 2026 post.
- AppRaven (appraven.net), a currently-active alternative, is a client-side
  JS app with no server-rendered HTML ("You need to enable JavaScript to
  run this app") - nothing for a plain `requests` scraper to read.
- AppsHunter.io and 148apps.com are still alive but are general app
  catalogs/gaming-news sites, not a clean "gone free today" listing.

iGeeksBlog (igeeksblog.com) is: it maintains one persistent, bookmarkable
page - not per-day archive URLs - with a "Today's Apps Gone Free" section
that it edits in place daily:
    https://www.igeeksblog.com/paid-iphone-apps-gone-free/
That's the primary (and, honestly, only) source this script scrapes today.

Every app it finds gets cross-checked against Apple's own iTunes Lookup
API (https://itunes.apple.com/lookup, documented at
performance-partners.apple.com) as a sanity check - if a plain "Free"
listing (not "Free+") no longer shows $0.00 there, the page is probably
stale for that entry, so it's dropped with a logged reason rather than
emailed. The lookup also fills in developer/genre/rating/description for
a nicer email, since iGeeksBlog's list itself is just icon + name + price.

ADDING A SECOND SOURCE
------------------------
The SOURCES list below is exactly one entry. If you find another site
worth scraping, write a `parse_<site>(html) -> [{"id", "name", "icon",
"url", "price_label"}, ...]` function (see parse_igeeksblog for the
shape) and append {"name": ..., "url": ..., "parser": ...} to SOURCES -
fetch_all_sources() already merges/dedupes across whatever's in that list.

USAGE
-----
    python apps_gone_free_emailer.py generate
        -> scrapes the source(s), cross-checks/enriches via iTunes Lookup,
           writes the composed email (subject/html/text) under ./email/,
           and updates the "already notified about this app" state file
    python apps_gone_free_emailer.py send
        -> reads ./email/* and sends it via Gmail SMTP

SETUP
-----
1. Install dependencies:
     pip install requests beautifulsoup4 certifi

2. Create a Gmail "App Password" (regular Gmail passwords won't work with SMTP):
     - https://myaccount.google.com/apppasswords
     - Needs 2-Step Verification turned on first.

3. Set these as environment variables (see README.md for GitHub Actions
   secrets instead, if running in the cloud):
     export GMAIL_ADDRESS="youraddress@gmail.com"
     export GMAIL_APP_PASSWORD="16-char-app-password"
     export APPS_RECIPIENT="where-to-send@example.com"
     export COUNTRY="us"                         # optional, App Store storefront for the Lookup cross-check
     export COOLDOWN_DAYS="21"                    # optional, don't re-email the same app within this many days
     export STATE_FILE="state/notified.json"      # optional, dedup state file
     export TIMEZONE="Asia/Ho_Chi_Minh"           # optional, for the subject line
     export ALWAYS_SEND="false"                   # optional, email even when there's nothing new
     export ALLOW_INSECURE_SSL_FALLBACK="false"   # optional, last-resort TLS bypass

NOTE ON SCRAPING
-----------------
Always worth checking the current robots.txt / terms before running this
unattended long-term: https://www.igeeksblog.com/robots.txt

iGeeksBlog's page markup can change at any time. (An earlier version of
this note theorized that a 0-apps run might be bot/anti-scraping
filtering treating this script's request differently than a browser's -
that turned out not to be it: a real 0-apps run's raw HTML showed the
actual page came through fine, just structured differently than
parse_igeeksblog() assumed at the time. HEADERS below still looks like
an ordinary current browser request, which can't hurt, but isn't the
main defense here.) Whenever a source parses to 0 apps,
fetch_all_sources() saves the raw response it actually received to
DEBUG_DIR (uploaded as a workflow artifact - see README's
"Troubleshooting" section) and logs whether "gone free" text shows up
anywhere in it at all - that's the fast way to tell "the real page came
through, parse_igeeksblog() needs adjusting to match a markup change"
apart from "this wasn't the real page at all," but either way, the
actual saved HTML is what settles it, not a guess. parse_igeeksblog()
itself targets iGeeksBlog's app-listing plugin ("WP-Appbox," visible in
an HTML comment around each entry) directly via its div.wpappbox /
.apptitle / .appicon / .price .value structure, confirmed against real
page source rather than inferred from a text-only rendering. Open the
page, view source, and adjust parse_igeeksblog() if it starts returning 0.
"""

import json
import os
import re
import smtplib
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import certifi
import requests
import urllib3
from bs4 import BeautifulSoup

if os.environ.get("ALLOW_INSECURE_SSL_FALLBACK", "false").lower() == "true":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Config ------------------------------------------------------------

COUNTRY = os.environ.get("COUNTRY", "us").strip().lower()
STATE_FILE = os.environ.get("STATE_FILE", "state/notified.json")
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", "21"))
STATE_RETENTION_DAYS = COOLDOWN_DAYS * 3  # how long entries stick around before being pruned entirely
EMAIL_DIR = "email"

LOOKUP_URL = "https://itunes.apple.com/lookup"
LOOKUP_BATCH_SIZE = 150
LOOKUP_BATCH_DELAY_SECONDS = 1.0

ALWAYS_SEND = os.environ.get("ALWAYS_SEND", "false").lower() == "true"
ALLOW_INSECURE_SSL_FALLBACK = os.environ.get("ALLOW_INSECURE_SSL_FALLBACK", "false").lower() == "true"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.google.com/",
}

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
APPS_RECIPIENT = os.environ.get("APPS_RECIPIENT")


# --- HTTP helper ---------------------------------------------------------

def http_get(url, params=None, timeout=20):
    """GET a URL, verifying TLS against certifi's CA bundle explicitly (same
    reasoning as the other emailers' fetch_page()). Raises on non-2xx."""
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=timeout, verify=certifi.where())
        resp.raise_for_status()
        return resp
    except requests.exceptions.SSLError as e:
        print(f"  TLS verification failed with certifi's CA bundle: {e}", file=sys.stderr)
        if not ALLOW_INSECURE_SSL_FALLBACK:
            print("  Set ALLOW_INSECURE_SSL_FALLBACK=true to retry without verification as a last resort.",
                  file=sys.stderr)
            raise
        print("  ALLOW_INSECURE_SSL_FALLBACK=true - retrying with TLS verification disabled.", file=sys.stderr)
        resp = requests.get(url, headers=HEADERS, params=params, timeout=timeout, verify=False)
        resp.raise_for_status()
        return resp


# --- Source: iGeeksBlog ---------------------------------------------------

IGEEKSBLOG_URL = os.environ.get("IGEEKSBLOG_URL", "https://www.igeeksblog.com/paid-iphone-apps-gone-free/")
APP_STORE_LINK_RE = re.compile(r"apps\.apple\.com/[a-z]{2}/app/[^/\s]+/id(\d+)", re.IGNORECASE)
# Matches the .price .value span's own text directly (get_text() on that span already
# concatenates the nested <sup>+</sup> in, so "Free+" arrives as one string - see
# parse_igeeksblog()). Deliberately excludes dollar amounts: if the "on sale" end-boundary
# heading is ever missed (markup change) and the walk spills into the SALE section, a paid
# app's "$X.XX" value simply won't match - silently skipped rather than risking a paid app
# being mislabeled as free.
GONE_FREE_VALUE_RE = re.compile(r"^free\+?$", re.IGNORECASE)


def _find_heading(soup, contains_text):
    """First heading-ish tag whose text contains `contains_text`
    (case-insensitive). Curly vs straight apostrophes ("Today's" vs
    "Today’s") are normalized away first so this doesn't depend on which
    one the page happens to use.

    Deliberately tries h2-h6 first and h1 dead last, not all six
    together: find_all() with a list of tag names returns matches in
    DOCUMENT ORDER, not grouped by level, and a page's own <h1> title
    will often itself contain whatever the body sections are about -
    here, literally "Today's Apps Gone Free on The App Store" - and
    that h1 sits near the top of the page, well before the real section
    heading. Searching all six together let that h1 win by document
    position every time, which produced a real 0-apps-parsed bug (the
    walk then started from the h1, hit the Table of Contents' own
    unrelated <h2> almost immediately, and stopped there). h2-h6 are
    reliably body section headings on essentially every blog/CMS, so
    they're tried first; the short-tag fallback after that covers
    page-builder blocks that skip semantic headings entirely; h1 is
    only consulted if genuinely nothing else matches anywhere.
    """
    needle = contains_text.lower()
    for tag in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
        t = tag.get_text(" ", strip=True).lower().replace("\u2019", "'")
        if needle in t:
            return tag
    for tag in soup.find_all(["div", "p", "span", "strong", "b", "a"]):
        t = tag.get_text(" ", strip=True).lower().replace("\u2019", "'")
        if needle in t and len(t) <= 80:
            return tag
    for tag in soup.find_all(["h1"]):
        t = tag.get_text(" ", strip=True).lower().replace("\u2019", "'")
        if needle in t:
            return tag
    return None


def parse_igeeksblog(html):
    """iGeeksBlog's page has a "Today's Apps Gone Free" section followed by
    a "Today's Apps on SALE" section (discounted, NOT free - deliberately
    excluded here, that's a different thing than what was asked for).

    Each app renders via a WordPress plugin ("WP-Appbox", visible in an
    HTML comment around each block) as a `div.wpappbox` with a
    consistent internal structure:
        <div class="wpappbox ...">
          <div class="appicon"><a href="APP_STORE_URL"><img src="ICON"></a></div>
          <a class="applinks" href="APP_STORE_URL"></a>
          <div class="appdetails">
            <div class="apptitle"><a href="APP_STORE_URL">NAME</a></div>
            <div class="price">
              <span class="label">Price: </span>
              <span class="value">Free<sup>+</sup></span>
            </div>
          </div>
        </div>
    Confirmed directly from the page's real HTML (not guessed from a
    text/markdown rendering, which strips exactly this kind of detail) -
    notably, "Price:" and the value are two SEPARATE spans, and "+" is
    its own nested <sup> - there's never one tag whose own text reads
    "Price: Free", which is why an earlier version of this parser (built
    by inference rather than against the real markup) found nothing.

    This still uses heading text to find the section boundaries (find_all_next,
    agnostic to exact class names, in case that part of the layout shifts),
    but within those boundaries now targets div.wpappbox specifically rather
    than a generic link-clustering heuristic - much less ambiguous given
    a real, named, consistently-structured component to anchor on.
    """
    soup = BeautifulSoup(html, "html.parser")

    start = _find_heading(soup, "gone free")
    if not start:
        return []
    end = _find_heading(soup, "on sale") or _find_heading(soup, "how to claim")

    apps = []
    seen_ids = set()
    for tag in start.find_all_next(True):  # True = any tag, in document order
        if end is not None and tag is end:
            break
        if tag.name in ("h2", "h3"):
            break  # some other section boundary we didn't expect - stop rather than over-read
        if tag.name != "div" or "wpappbox" not in (tag.get("class") or []):
            continue

        link = tag.select_one(".apptitle a") or tag.select_one(".appicon a")
        if not link:
            continue
        m = APP_STORE_LINK_RE.search(link.get("href", ""))
        if not m:
            continue
        app_id = m.group(1)
        if app_id in seen_ids:
            continue

        value_el = tag.select_one(".price .value")
        price_text = value_el.get_text(strip=True) if value_el else ""
        if not GONE_FREE_VALUE_RE.match(price_text):
            continue  # e.g. a dollar amount - not actually free, don't include it

        icon_el = tag.select_one(".appicon img")
        icon = icon_el.get("src", "").strip() if icon_el else ""
        if icon.startswith("//"):
            icon = "https:" + icon  # protocol-relative URLs don't render reliably in email

        seen_ids.add(app_id)
        apps.append({
            "id": app_id,
            "name": link.get_text(strip=True) or link.get("aria-label", "").strip() or "Unknown app",
            "icon": icon,
            "url": f"https://apps.apple.com/app/id{app_id}",
            "price_label": price_text,
            "source": "iGeeksBlog",
        })
    return apps


SOURCES = [
    {"name": "iGeeksBlog", "url": IGEEKSBLOG_URL, "parser": parse_igeeksblog},
    # Add more sites here as {"name": ..., "url": ..., "parser": parse_fn} -
    # see the module docstring ("ADDING A SECOND SOURCE").
]


DEBUG_DIR = "debug"


def fetch_all_sources():
    """Fetches + parses every entry in SOURCES, tolerating any one of them
    failing (same graceful-degradation spirit as currency-rate-emailer's
    per-source try/except). Dedupes by app id across sources, first
    source in the list wins on a duplicate.

    Whenever a source parses to 0 apps, the raw response is saved under
    DEBUG_DIR and a same-page substring check is logged - this is meant
    to distinguish two very different failure modes without needing to
    guess: "the real page came through but doesn't match the parser's
    assumptions anymore" (fixable by adjusting the parser) vs "this
    response isn't the real page at all" (e.g. a bot-check/consent page,
    or a JS-shell HTML if the site's prerendering treats this script's
    request differently than a browser's - the raw file lands in the
    'debug-html' workflow artifact either way, see README)."""
    seen_ids = set()
    all_apps = []
    for source in SOURCES:
        try:
            resp = http_get(source["url"])
            apps = source["parser"](resp.text)
            print(f"  {source['name']}: parsed {len(apps)} app(s) from {source['url']}")
            if not apps:
                looks_relevant = "gone free" in resp.text.lower() or "apps.apple.com" in resp.text.lower()
                if looks_relevant:
                    explanation = ("the content looks like the real page, so the parser most "
                                    "likely needs adjusting to match a markup change")
                else:
                    explanation = ("this response may not be the real page at all "
                                    "(bot/consent check, or an unrendered JS shell)")
                print(f"  {source['name']} returned 0 apps (HTTP {resp.status_code}, "
                      f"{len(resp.text)} chars). 'gone free' or an App Store link "
                      f"{'DOES' if looks_relevant else 'does NOT'} appear anywhere in the raw "
                      f"response - {explanation}.",
                      file=sys.stderr)
                os.makedirs(DEBUG_DIR, exist_ok=True)
                debug_path = os.path.join(DEBUG_DIR, f"{source['name'].lower().replace(' ', '_')}_raw.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(resp.text)
                print(f"  saved raw response to {debug_path} for inspection "
                      f"(uploaded as a workflow artifact - see README).", file=sys.stderr)
            for app in apps:
                if app["id"] not in seen_ids:
                    seen_ids.add(app["id"])
                    all_apps.append(app)
        except requests.RequestException as e:
            print(f"  {source['name']} fetch failed: {e}", file=sys.stderr)
    return all_apps


# --- Enrichment + cross-check: iTunes Lookup ------------------------------

def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def lookup_apps(app_ids, country=COUNTRY):
    """Batched iTunes Lookup calls. Returns {id: record}. Tolerant of the
    whole thing failing - caller treats a missing id as "couldn't verify",
    not as "doesn't exist"."""
    records = {}
    unique_ids = list(dict.fromkeys(app_ids))
    if not unique_ids:
        return records
    batches = list(chunked(unique_ids, LOOKUP_BATCH_SIZE))
    for i, batch in enumerate(batches):
        params = {"id": ",".join(batch), "country": country, "entity": "software"}
        try:
            resp = http_get(LOOKUP_URL, params=params)
            data = resp.json()
            for item in data.get("results", []):
                app_id = str(item.get("trackId", ""))
                if not app_id:
                    continue
                records[app_id] = {
                    "developer": item.get("artistName") or item.get("sellerName") or "",
                    "price": float(item.get("price") or 0.0),
                    "url": item.get("trackViewUrl") or "",
                    "icon": item.get("artworkUrl100") or item.get("artworkUrl60") or "",
                    "genre": item.get("primaryGenreName", ""),
                    "rating": item.get("averageUserRating"),
                    "rating_count": item.get("userRatingCount", 0),
                    "description": (item.get("description") or "").strip(),
                }
        except (requests.RequestException, ValueError) as e:
            print(f"  lookup batch {i + 1}/{len(batches)} failed: {e}", file=sys.stderr)
        if i + 1 < len(batches):
            time.sleep(LOOKUP_BATCH_DELAY_SECONDS)
    return records


def enrich_and_verify(apps, country=COUNTRY):
    """Fills in developer/genre/rating/description from the Lookup API, and
    drops entries the Lookup API contradicts. The only entries this can
    actually contradict are plain "Free" ones (previously a paid, one-time
    purchase, now $0 to download): the Lookup API's `price` field reflects
    the CURRENT download price, so a plain "Free" listing that no longer
    shows $0.00 there means the page is stale for that app. "Free+" apps
    (free to download with the premium tier unlocked, normally an
    in-app-purchase/subscription) always show $0.00 in Lookup regardless
    of whether the unlock promo is still live, since the download itself
    is always free either way - so Lookup can't verify or contradict
    those, and they're passed through on the source site's word alone.

    If the Lookup API is unreachable entirely, every app is kept as-is
    (scraped fields only) rather than blocking the email on an
    enrichment step that's explicitly a nice-to-have.
    """
    records = lookup_apps([a["id"] for a in apps], country=country)
    if not records:
        print("  lookup returned nothing (or failed) - proceeding with un-enriched scrape data.")
        return apps

    kept = []
    for app in apps:
        record = records.get(app["id"])
        if record is None:
            kept.append(app)  # couldn't verify (region-locked, delisted, transient miss) - trust the source
            continue
        is_plain_free = app["price_label"].strip().lower() == "free"
        if is_plain_free and record["price"] > 0:
            print(f"  dropping {app['name']!r}: iGeeksBlog lists it as Free but iTunes Lookup shows "
                  f"a price of {record['price']} now - likely stale.", file=sys.stderr)
            continue
        merged = {**app}
        merged["developer"] = record["developer"]
        merged["genre"] = record["genre"]
        merged["rating"] = record["rating"]
        merged["rating_count"] = record["rating_count"]
        merged["description"] = record["description"]
        # Prefer Lookup's own artwork/URL when present - marginally more
        # likely to be current than whatever iGeeksBlog embedded.
        merged["icon"] = record["icon"] or app["icon"]
        merged["url"] = record["url"] or app["url"]
        kept.append(merged)
    return kept


# --- Dedup state ------------------------------------------------------------

def today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_state(path=STATE_FILE):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  could not read {path} ({e}) - starting with empty state", file=sys.stderr)
        return {}


def save_state(state, path=STATE_FILE):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)


def split_new_and_repeat(apps, state, cooldown_days=COOLDOWN_DAYS):
    """An app is 'new' if we've never notified about it, or last did
    more than cooldown_days ago (so a promo that resurfaces months later
    is still treated as news, but a multi-day promo doesn't get re-sent
    every single run while it's still listed)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).strftime("%Y-%m-%d")
    new_apps, repeat_apps = [], []
    for app in apps:
        prior = state.get(app["id"])
        if prior and prior.get("notified_on", "0000-00-00") >= cutoff:
            repeat_apps.append(app)
        else:
            new_apps.append(app)
    return new_apps, repeat_apps


def update_state(state, notified_apps):
    today = today_str()
    new_state = dict(state)
    for app in notified_apps:
        new_state[app["id"]] = {"name": app["name"], "notified_on": today}
    retention_cutoff = (datetime.now(timezone.utc) - timedelta(days=STATE_RETENTION_DAYS)).strftime("%Y-%m-%d")
    for app_id in list(new_state.keys()):
        if new_state[app_id].get("notified_on", "0000-00-00") < retention_cutoff:
            new_state.pop(app_id, None)
    return new_state


# --- Formatting ---------------------------------------------------------

def truncate(text, max_len=220):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def star_string(rating):
    if not rating:
        return ""
    full = round(rating)
    return "★" * full + "☆" * (5 - full)


def price_badge(price_label):
    is_plus = price_label.strip().lower() != "free"
    label = "FREE+" if is_plus else "FREE"
    sub = "free download, premium unlocked for now" if is_plus else "was a paid download"
    return label, sub


def build_html(new_apps, timestamp, stats):
    if not new_apps:
        cards = "<p style='color:#555;'>Nothing new since the last check.</p>"
    else:
        card_rows = []
        for app in new_apps:
            rating_html = ""
            if app.get("rating"):
                rating_html = (
                    f"<span style='color:#f5a623'>{escape(star_string(app['rating']))}</span> "
                    f"<span style='color:#999'>{app['rating']:.1f} ({app.get('rating_count', 0):,})</span>"
                )
            icon_html = (
                f"<img src='{escape(app['icon'])}' width='64' height='64' "
                f"style='border-radius:14px;display:block' alt=''>"
                if app.get("icon") else ""
            )
            badge, badge_sub = price_badge(app["price_label"])
            genre_bits = " · ".join(x for x in [app.get("developer", ""), app.get("genre", "")] if x)
            card_rows.append(f"""
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;max-width:680px;margin:0 0 14px;border:1px solid #eee;border-radius:12px;">
  <tr>
    <td style="width:80px;padding:14px 0 14px 14px;vertical-align:top;">{icon_html}</td>
    <td style="padding:14px;vertical-align:top;font-family:Arial,Helvetica,sans-serif;">
      <div style="font-size:16px;font-weight:bold;color:#111;">
        <a href="{escape(app['url'])}" style="color:#0a66c2;text-decoration:none;">{escape(app['name'])}</a>
      </div>
      <div style="font-size:13px;color:#666;margin:2px 0 6px;">{escape(genre_bits)}</div>
      <div style="font-size:13px;margin-bottom:6px;">{rating_html}</div>
      <div style="font-size:13px;color:#333;line-height:1.4;">{escape(truncate(app.get('description', '')))}</div>
      <div style="margin-top:8px;">
        <span style="background:#e8f5e9;color:#1b5e20;font-weight:bold;padding:3px 8px;border-radius:6px;font-size:13px;">{badge}</span>
        <span style="color:#999;margin-left:6px;font-size:12px;">{escape(badge_sub)}</span>
      </div>
    </td>
  </tr>
</table>""")
        cards = "\n".join(card_rows)

    return f"""\
<html>
<body style="margin:0; padding:20px; background:#f4f4f4; font-family:Arial,Helvetica,sans-serif;">
  <h1 style="color:#1a5fb4;">iOS Apps Gone Free</h1>
  <p style="color:#555;">Checked {escape(timestamp)} · {stats['scraped']} app(s) found today, {stats['new']} new, {stats['repeat']} already sent within the last {COOLDOWN_DAYS} days</p>
  {cards}
  <p style="color:#999; font-size:12px; margin-top:24px;">
    Source: <a href="{escape(IGEEKSBLOG_URL)}">iGeeksBlog - Today's Apps Gone Free</a>, cross-checked against
    Apple's iTunes Lookup API (country={escape(COUNTRY)}) · "FREE+" means the app itself was already free to
    download and a premium/subscription tier has been unlocked for now, not that the whole app was a paid
    download · Promotions can end at any time - check the App Store link before assuming it's still free.
  </p>
</body>
</html>"""


def build_plain_text(new_apps, timestamp, stats):
    lines = [
        f"iOS Apps Gone Free - checked {timestamp}",
        f"{stats['scraped']} app(s) found today, {stats['new']} new, "
        f"{stats['repeat']} already sent within the last {COOLDOWN_DAYS} days",
        "",
    ]
    if not new_apps:
        lines.append("Nothing new since the last check.")
    else:
        for app in new_apps:
            badge, badge_sub = price_badge(app["price_label"])
            lines.append(f"- {app['name']} ({badge} - {badge_sub})")
            meta_bits = " | ".join(x for x in [app.get("developer", ""), app.get("genre", "")] if x)
            if app.get("rating"):
                meta_bits += f" | {app['rating']:.1f}* ({app.get('rating_count', 0)})"
            if meta_bits:
                lines.append(f"  {meta_bits}")
            if app.get("description"):
                lines.append(f"  {truncate(app['description'], 200)}")
            lines.append(f"  {app['url']}")
            lines.append("")
    return "\n".join(lines)


def resolve_timestamp():
    timezone_name = os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh")
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.now()
    return now, now.strftime("%H:%M %d/%m/%Y")


# --- Commands -----------------------------------------------------------

def cmd_generate():
    if os.path.exists(EMAIL_DIR):
        for f in os.listdir(EMAIL_DIR):
            os.remove(os.path.join(EMAIL_DIR, f))
    os.makedirs(EMAIL_DIR, exist_ok=True)

    old_state = load_state()

    print("Fetching source(s) ...")
    scraped = fetch_all_sources()
    print(f"  {len(scraped)} app(s) total after merging sources.")

    if not scraped:
        print("0 apps scraped from every source this run - probably a scraper/markup problem, not a quiet day. "
              "Aborting without sending or touching state.", file=sys.stderr)
        with open(os.path.join(EMAIL_DIR, "meta.json"), "w") as f:
            json.dump({"send": False, "scraped": 0, "new": 0, "repeat": 0}, f)
        return

    print(f"Cross-checking/enriching via iTunes Lookup (country={COUNTRY}) ...")
    verified = enrich_and_verify(scraped)
    print(f"  {len(verified)}/{len(scraped)} app(s) kept after verification.")

    new_apps, repeat_apps = split_new_and_repeat(verified, old_state)
    stats = {"scraped": len(verified), "new": len(new_apps), "repeat": len(repeat_apps)}
    print(f"Result: {stats['new']} new, {stats['repeat']} repeat (already notified within {COOLDOWN_DAYS} days).")

    new_state = update_state(old_state, new_apps)
    save_state(new_state)

    if not new_apps and not ALWAYS_SEND:
        print("Nothing new this run and ALWAYS_SEND=false - skipping email.")
        with open(os.path.join(EMAIL_DIR, "meta.json"), "w") as f:
            json.dump({"send": False, **stats}, f)
        return

    now, timestamp = resolve_timestamp()
    if new_apps:
        subject = f"{len(new_apps)} iOS app(s) gone free - {now.strftime('%d/%m/%Y %H:%M')}"
    else:
        subject = f"iOS Apps Gone Free - nothing new today - {now.strftime('%d/%m/%Y %H:%M')}"

    html_body = build_html(new_apps, timestamp, stats)
    text_body = build_plain_text(new_apps, timestamp, stats)

    with open(os.path.join(EMAIL_DIR, "subject.txt"), "w", encoding="utf-8") as f:
        f.write(subject)
    with open(os.path.join(EMAIL_DIR, "body.html"), "w", encoding="utf-8") as f:
        f.write(html_body)
    with open(os.path.join(EMAIL_DIR, "body.txt"), "w", encoding="utf-8") as f:
        f.write(text_body)
    with open(os.path.join(EMAIL_DIR, "meta.json"), "w") as f:
        json.dump({"send": True, **stats}, f)

    print(f"Generated email ({len(new_apps)} new app(s)). Saved to ./{EMAIL_DIR}/")


def cmd_send():
    missing = [name for name, val in [
        ("GMAIL_ADDRESS", GMAIL_ADDRESS),
        ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
        ("APPS_RECIPIENT", APPS_RECIPIENT),
    ] if not val]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    meta_path = os.path.join(EMAIL_DIR, "meta.json")
    if not os.path.exists(meta_path):
        print("No meta.json found - run 'generate' first.", file=sys.stderr)
        sys.exit(1)
    with open(meta_path) as f:
        meta = json.load(f)
    if not meta.get("send", False):
        print("Nothing to send this run.")
        return

    with open(os.path.join(EMAIL_DIR, "subject.txt"), encoding="utf-8") as f:
        subject = f.read()
    with open(os.path.join(EMAIL_DIR, "body.html"), encoding="utf-8") as f:
        html_body = f.read()
    with open(os.path.join(EMAIL_DIR, "body.txt"), encoding="utf-8") as f:
        text_body = f.read()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = APPS_RECIPIENT
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"Sent to {APPS_RECIPIENT}!")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("generate", "send"):
        print("Usage: python apps_gone_free_emailer.py [generate|send]", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "generate":
        cmd_generate()
    else:
        cmd_send()


if __name__ == "__main__":
    main()
