#!/usr/bin/env python3
"""
apps_gone_free_emailer.py

Daily "iOS apps gone free" digest -> email (runs on GitHub Actions, no local
computer needed). Same generate/send two-phase shape, Gmail-SMTP delivery,
and dedup-via-state-branch trick as gold-price-emailer / house-price-emailer
/ tech-price-mailer / currency-rate-emailer.

THREE SOURCES, AND WHY NOT JUST ONE
--------------------------------------
A lot of the well-known "apps gone free" trackers people remember are dead:
AppShopper (shut down 2021), iOSnoops (shut down since), AppAdvice's list
(stopped updating early 2026). AppRaven is JS-only with nothing for a
plain scraper to read. AppsHunter.io/148apps are general catalogs, not a
clean "gone free" list. AppStore-Discounts.com would've been ideal but its
robots.txt disallows automated access. PSprices.com turned out to be a
console/PC gaming tracker. Reddit r/AppHookup's format is too inconsistent
to parse reliably without auth. Yitake.in reads as templated filler. Full
history of what was checked and why each was ruled out: README.md's
"Important: read this before relying on it" table.

Given how thin that leaves things, this doesn't lean on any one source:

1. iGeeksBlog (igeeksblog.com) - one persistent, bookmarkable page it
   edits in place daily. parse_igeeksblog() targets its "WP-Appbox"
   listing plugin directly (div.wpappbox / .apptitle / .appicon /
   .price .value), confirmed against real page source. Ids come
   straight from a real apps.apple.com link on the page - certain, not
   guessed (see SOURCES_WITH_CERTAIN_IDS).
2. AppDovo (appdovo.com) - a mixed iOS+Android, free+discounted feed;
   parse_appdovo() filters to iOS + exactly 100% off. Its own links go
   to AppDovo's site, not the App Store, so the id is inferred from a
   digit run in AppDovo's cached icon filenames - a reasonable bet, not
   a certainty, so these entries get a stricter identity check in
   enrich_and_verify() (lookup match AND name match required, or
   dropped) rather than the benefit of the doubt a certain id gets.
3. Apple's own top-paid chart feed (rss.applemarketingtools.com,
   discover_chart_gone_free()) - no scraping at all, auto-discovers
   popular paid apps and reports genuine price-drops-to-$0 between
   runs. Structurally immune to the markup breakage that hit both
   scrapers above at various points while this was being built.

Every scraped app (sources 1-2) is cross-checked against Apple's own
iTunes Lookup API (https://itunes.apple.com/lookup) - a plain "Free"
listing that no longer shows $0.00 there gets dropped as stale. "Free+"
listings can't be verified on price the same way (a free-to-download app
always shows $0.00 in Lookup, promo or not), so those pass through on
the source's word alone, subject to the identity check above for
non-certain ids. The lookup also fills in developer/genre/rating/
description for a nicer email either way.

Any one (or two) of the three sources failing no longer means an empty
inbox - see cmd_generate()'s "Every source found 0 apps" check for the
one case where it still does (all three genuinely down at once).

ADDING ANOTHER SOURCE
------------------------
Two extension points: another *scraped* site goes in the SOURCES list
below (see parse_igeeksblog() or parse_appdovo() for the shape,
depending on whether the site links directly to the App Store or not);
another *official API* worth polling the same way as Apple's chart feed
follows discover_chart_gone_free()'s pattern instead, independent of
SOURCES entirely. Full guidance: README.md's "Adding another source".

ICON REHOSTING (OPTIONAL, GITHUB ACTIONS ONLY)
-------------------------------------------------
rehost_icons() can download each newly-free app's icon and rewrite its
URL to a raw.githubusercontent.com location a workflow step publishes
it to - mirrors 9gag-meme-emailer's meme-assets-branch pattern. Off by
default (ICON_ASSETS_DIR unset); local runs and `preview` are always
unaffected regardless. Full discussion of why this isn't solving a
problem Apple's own icon CDN actually has, adopted anyway for
consistency with the rest of the project family: README.md's "Icon
hosting".

USAGE
-----
    python apps_gone_free_emailer.py generate
        -> runs all three sources, cross-checks/enriches the scraped ones
           via iTunes Lookup, writes the composed email (subject/html/text)
           under ./email/, and updates the two state files (notified-apps
           dedup + chart price-history)
    python apps_gone_free_emailer.py send
        -> reads ./email/* and sends it via Gmail SMTP
    python apps_gone_free_emailer.py preview
        -> writes preview.html / preview.txt from sample data through the
           real template functions - no network, no state touched, nothing
           sent. Use this to check the design after editing build_html()
           or build_preview_page_html().

SETUP
-----
1. Install dependencies:
     pip install requests beautifulsoup4 certifi

2. Create a Gmail "App Password" (regular Gmail passwords won't work with SMTP):
     - https://myaccount.google.com/apppasswords
     - Needs 2-Step Verification turned on first.

3. Set these as environment variables (see README.md for GitHub Actions
   secrets instead, if running in the cloud; README.md's "Configuration"
   section has the full list including chart/icon-rehosting settings):
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
unattended long-term: https://www.igeeksblog.com/robots.txt and
https://appdovo.com/robots.txt

Either scraped site's markup can change at any time. (An earlier version
of this note theorized that a 0-apps run might be bot/anti-scraping
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
through, the parser needs adjusting to match a markup change" apart
from "this wasn't the real page at all," but either way, the actual
saved HTML is what settles it, not a guess. parse_igeeksblog() itself
targets iGeeksBlog's app-listing plugin ("WP-Appbox," visible in an
HTML comment around each entry) directly via its div.wpappbox /
.apptitle / .appicon / .price .value structure, confirmed against real
page source rather than inferred from a text-only rendering. Open the
page, view source, and adjust the relevant parse_<site>() function if
it starts returning 0.
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

# Bumped whenever parse_igeeksblog() or _find_heading() changes meaningfully.
# Printed at the start of every `generate` run specifically so a log is
# self-describing about which fix actually ran, rather than needing to
# diff file contents by hand to answer "is this the latest version?"
SCRIPT_VERSION = "2026-08-02.10 (docs/footer consistency audit - AppDovo credit + stats fix)"

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


APPDOVO_URL = os.environ.get("APPDOVO_URL", "https://appdovo.com/apps-gone-free-today/")
APPDOVO_ICON_ID_RE = re.compile(r"/(\d{8,12})[A-Za-z]")  # leading digit run in AppDovo's cached icon filenames


def parse_appdovo(html):
    """AppDovo mixes iOS + Android and fully-free + merely-discounted
    entries in one unified list (no separate "gone free" vs "on sale"
    sections the way iGeeksBlog has), so this filters for both: platform
    tag exactly "iOS" (not "android"), and current price exactly "FREE"
    (not just some % off).

    Unlike iGeeksBlog, this listing page's own links go to AppDovo's own
    site (/apps/<slug>/), not directly to the App Store - there's no
    apps.apple.com link on this page to read a certain id from. Instead
    this reads a leading digit run AppDovo embeds in its own cached icon
    filenames (e.g. ".../6774355361AppIcon-....jpg"), which matches
    Apple's id format closely enough to be a reasonable bet - but it IS a
    bet, not a certainty the way iGeeksBlog's id is. See
    SOURCES_WITH_CERTAIN_IDS / enrich_and_verify(): AppDovo is
    deliberately left out of that set, so a wrong guess here gets caught
    and dropped by the stricter identity check there (no match, or a
    name that doesn't line up) rather than shipping a broken or
    mismatched App Store link.

    Also worth flagging: built from a fetched/rendered copy of the page
    text, not raw HTML - AppDovo wasn't available for the same direct
    view-source inspection iGeeksBlog eventually was, so treat this the
    same way iGeeksBlog's very first version should have been treated:
    a best effort, protected by the same debug-artifact safety net if
    the real markup turns out to disagree with what this assumes.
    """
    soup = BeautifulSoup(html, "html.parser")
    apps = []
    seen_ids = set()
    for img in soup.find_all("img", src=True):
        m = APPDOVO_ICON_ID_RE.search(img["src"])
        if not m:
            continue
        candidate_id = m.group(1)
        if candidate_id in seen_ids:
            continue

        lines = []
        for tag in img.find_all_next(True):
            if tag.name == "img":
                break  # reached the next app's card - this one's done
            if tag.name == "a" and re.search(r"view details", tag.get_text(strip=True), re.IGNORECASE):
                break  # reached this app's own closing link - also done
            if not tag.find(True):  # leaf-ish text node
                text = tag.get_text(strip=True)
                if text:
                    lines.append(text)
        if not lines:
            continue

        platform, name, is_free = None, None, False
        for line in lines:
            pf = re.match(r"^(iOS|android)\b", line, re.IGNORECASE)
            if pf and platform is None:
                platform = pf.group(1)
                continue
            if re.fullmatch(r"free", line, re.IGNORECASE):
                is_free = True
                continue
            if name is None and not re.match(r"^\$[\d.,]+$|^\d+%\s*off$", line, re.IGNORECASE):
                name = line

        if platform and platform.lower() == "ios" and is_free and name:
            seen_ids.add(candidate_id)
            apps.append({
                "id": candidate_id,
                "name": name,
                "icon": img["src"],
                "url": f"https://apps.apple.com/app/id{candidate_id}",
                "price_label": "Free",
                "source": "AppDovo",
            })
    return apps


SOURCES = [
    {"name": "iGeeksBlog", "url": IGEEKSBLOG_URL, "parser": parse_igeeksblog},
    {"name": "AppDovo", "url": APPDOVO_URL, "parser": parse_appdovo},
    # Add more sites here as {"name": ..., "url": ..., "parser": parse_fn} -
    # see the module docstring ("ADDING A SECOND SOURCE"). Remember to add
    # the source's "name" to SOURCES_WITH_CERTAIN_IDS too, but only if its
    # ids are read directly from a real apps.apple.com link on the page -
    # if they're inferred/guessed the way AppDovo's are, leave it out so
    # enrich_and_verify() applies the stricter identity check instead.
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
                    "name": item.get("trackName", "Unknown app"),
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


SOURCES_WITH_CERTAIN_IDS = {"iGeeksBlog"}  # id read directly from a real apps.apple.com link - a failed
# lookup for these just means transient/region-locked/delisted, so the entry is kept and trusted as-is.
# Any OTHER source's id is treated as a guess (see parse_appdovo() for why) - a failed lookup for those
# almost certainly means the guess itself was wrong, so the entry gets dropped rather than trusted.


def names_roughly_match(a, b):
    """Loose match for cross-checking a guessed id's looked-up name against
    the name a source actually scraped - not exact-string comparison,
    since sources often abbreviate/punctuate app names slightly
    differently (e.g. app's own "NeonVortex" vs a listing site's "Neon
    Vortex"). Case/punctuation/whitespace-insensitive substring check in
    either direction is intentionally forgiving; the id itself being
    guessed correctly is what actually matters here, and a name that's
    not even a partial match either way is a strong signal it wasn't."""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def enrich_and_verify(apps, country=COUNTRY):
    """Fills in developer/genre/rating/description from the Lookup API, and
    drops entries the Lookup API contradicts. The only entries this can
    actually contradict on PRICE are plain "Free" ones (previously a
    paid, one-time purchase, now $0 to download): the Lookup API's
    `price` field reflects the CURRENT download price, so a plain "Free"
    listing that no longer shows $0.00 there means the page is stale for
    that app. "Free+" apps (free to download with the premium tier
    unlocked, normally an in-app-purchase/subscription) always show
    $0.00 in Lookup regardless of whether the unlock promo is still live,
    since the download itself is always free either way - so Lookup
    can't verify or contradict those on price, and they're passed
    through on the source site's word alone (unless their id fails the
    identity check below).

    Separately, on IDENTITY: SOURCES_WITH_CERTAIN_IDS get the benefit of
    the doubt if Lookup simply doesn't return a record (transient miss,
    region lock, delisted - the id itself was never in question). Any
    other source's id is a guess (see parse_appdovo()), so for those, no
    record OR a record whose name doesn't reasonably match what was
    scraped means the guess was probably wrong - dropped rather than
    risking a broken or mismatched App Store link in the email.

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
        id_is_certain = app.get("source") in SOURCES_WITH_CERTAIN_IDS
        if record is None:
            if id_is_certain:
                kept.append(app)  # couldn't verify (region-locked, delisted, transient miss) - trust the source
            else:
                print(f"  dropping {app['name']!r} from {app.get('source')}: no iTunes Lookup match for "
                      f"guessed id {app['id']} - the guess was probably wrong.", file=sys.stderr)
            continue
        if not id_is_certain and not names_roughly_match(app["name"], record["name"]):
            print(f"  dropping {app['name']!r} from {app.get('source')}: guessed id {app['id']} resolved to "
                  f"a different app ({record['name']!r}) - wrong guess.", file=sys.stderr)
            continue
        is_plain_free = app["price_label"].strip().lower() == "free"
        if is_plain_free and record["price"] > 0:
            print(f"  dropping {app['name']!r}: {app.get('source')} lists it as Free but iTunes Lookup shows "
                  f"a price of {record['price']} now - likely stale.", file=sys.stderr)
            continue
        merged = {**app}
        merged["developer"] = record["developer"]
        merged["genre"] = record["genre"]
        merged["rating"] = record["rating"]
        merged["rating_count"] = record["rating_count"]
        merged["description"] = record["description"]
        # Prefer Lookup's own artwork/URL when present - marginally more
        # likely to be current than whatever the source embedded.
        merged["icon"] = record["icon"] or app["icon"]
        merged["url"] = record["url"] or app["url"]
        kept.append(merged)
    return kept


# --- Source 2: Apple's own top-paid chart + price-drop detection -----------
#
# iGeeksBlog is a hand-curated editorial list - useful, but it's scraped
# HTML, and scraped HTML can (and, this week, did - three times) break in
# ways that have nothing to do with whether any apps actually went free.
# This second source is structurally immune to that failure mode: no HTML,
# no markup to break. It auto-discovers popular paid apps from Apple's own
# public top-paid chart feed, remembers each one's price between runs (in
# CHART_STATE_FILE), and reports any that have dropped to $0.00 since the
# last check - using the exact same iTunes Lookup API this script already
# depends on for enrichment above, just called on a schedule instead of
# once per scraped id.
#
# Trade-off worth being upfront about: this only sees apps popular enough
# to be in the top CHART_LIMIT paid apps to begin with, so it won't catch
# a niche app going free the way an editor hand-picking submissions might.
# The two sources have different blind spots, which is the actual point
# of having both rather than two attempts at the same thing.

CHART_URL_TEMPLATE = "https://rss.applemarketingtools.com/api/v2/{country}/apps/top-paid/{limit}/apps.json"
CHART_LIMIT = int(os.environ.get("CHART_LIMIT", "100"))
CHART_FALLBACK_LIMIT = 100  # the endpoint informally 500s above ~100 as of 2026; see fetch_top_paid_ids()
CHART_FETCH_RETRIES = int(os.environ.get("CHART_FETCH_RETRIES", "3"))  # retries per limit on transient network errors
CHART_FETCH_RETRY_DELAY = int(os.environ.get("CHART_FETCH_RETRY_DELAY", "5"))  # seconds between retries
CHART_STATE_FILE = os.environ.get("CHART_STATE_FILE", "state/chart_candidates.json")
CHART_MAX_TRACK_AGE_DAYS = int(os.environ.get("CHART_MAX_TRACK_AGE_DAYS", "21"))
CHART_MAX_TRACKED_APPS = int(os.environ.get("CHART_MAX_TRACKED_APPS", "2000"))
CHART_MAX_CONSECUTIVE_MISSES = 3


def fetch_top_paid_ids(country=COUNTRY, limit=CHART_LIMIT):
    """Returns a list of App Store id strings from Apple's top-paid chart
    feed. Two independent layers of retry here, for two different failure
    modes: falls back to CHART_FALLBACK_LIMIT if the requested limit
    itself gets rejected (the endpoint's own constraints), and separately
    retries CHART_FETCH_RETRIES times on transient network errors
    (timeouts, connection resets) at whichever limit is being tried -
    when limit already equals CHART_FALLBACK_LIMIT (the default case),
    the limit-fallback loop only ever runs once, so without this second
    layer a single transient timeout had zero cushion at all."""
    tried = []
    for this_limit in dict.fromkeys([limit, CHART_FALLBACK_LIMIT]):
        tried.append(this_limit)
        url = CHART_URL_TEMPLATE.format(country=country, limit=this_limit)
        for attempt in range(1, CHART_FETCH_RETRIES + 1):
            try:
                resp = http_get(url)
                data = resp.json()
                results = data.get("feed", {}).get("results", [])
                ids = [r["id"] for r in results if r.get("id")]
                if ids:
                    if this_limit != limit:
                        print(f"  (chart: used fallback limit={this_limit} after limit={limit} failed)", file=sys.stderr)
                    return ids
                print(f"  chart fetch at limit={this_limit} returned 0 ids.", file=sys.stderr)
                break  # got a real response, just empty - retrying won't change that; try the next limit instead
            except (requests.RequestException, ValueError) as e:
                if attempt < CHART_FETCH_RETRIES:
                    print(f"  chart fetch at limit={this_limit} failed (attempt {attempt}/{CHART_FETCH_RETRIES}): "
                          f"{e} - retrying in {CHART_FETCH_RETRY_DELAY}s...", file=sys.stderr)
                    time.sleep(CHART_FETCH_RETRY_DELAY)
                else:
                    print(f"  chart fetch at limit={this_limit} failed after {CHART_FETCH_RETRIES} attempts: {e}",
                          file=sys.stderr)
    print(f"  giving up on chart discovery this run (tried limits {tried}).", file=sys.stderr)
    return []


def discover_chart_gone_free(chart_state, country=COUNTRY):
    """Folds this run's chart + lookup results into chart_state, prunes it,
    and returns (newly_free_apps, updated_chart_state). An app only counts
    as newly free if chart_state already had a price > 0 for it from a
    previous run - first-ever observation of any app is a baseline, not
    an event, same reasoning as the scraped-source dedup."""
    chart_ids = fetch_top_paid_ids(country=country)
    print(f"  chart: {len(chart_ids)} id(s) from today's top-paid chart.")
    checked_ids = list(dict.fromkeys(list(chart_state.keys()) + chart_ids))
    if not checked_ids:
        return [], chart_state

    fresh_records = lookup_apps(checked_ids, country=country)
    print(f"  chart: got current prices for {len(fresh_records)}/{len(checked_ids)} tracked app(s).")

    today = today_str()
    new_state = dict(chart_state)
    newly_free = []
    for app_id in checked_ids:
        record = fresh_records.get(app_id)
        prior = new_state.get(app_id, {})
        if record is not None:
            if prior.get("price", 0) > 0 and record["price"] == 0:
                newly_free.append({
                    "id": app_id,
                    "name": record["name"],
                    "developer": record["developer"],
                    "icon": record["icon"],
                    "url": record["url"] or f"https://apps.apple.com/app/id{app_id}",
                    "genre": record["genre"],
                    "rating": record["rating"],
                    "rating_count": record["rating_count"],
                    "description": record["description"],
                    "price_label": "Free",
                    "source": "Apple Top-Paid Chart",
                })
            new_state[app_id] = {
                "name": record["name"], "price": record["price"],
                "first_seen": prior.get("first_seen", today), "last_checked": today, "misses": 0,
            }
        elif prior:
            misses = prior.get("misses", 0) + 1
            if misses >= CHART_MAX_CONSECUTIVE_MISSES:
                new_state.pop(app_id, None)
            else:
                new_state[app_id] = {**prior, "misses": misses, "last_checked": today}

    # Age-based prune, same reasoning as the scraped-source state: a
    # candidate that's been tracked for weeks and never gone free is
    # probably just a stable paid app - stop watching it to keep the
    # state file bounded. Keyed off first_seen, not last_checked, for
    # the same reason as the other state: every checked_id gets
    # last_checked refreshed every run, so a last_checked cutoff would
    # never fire.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CHART_MAX_TRACK_AGE_DAYS)).strftime("%Y-%m-%d")
    for app_id in list(new_state.keys()):
        entry = new_state[app_id]
        if entry.get("price", 0) == 0:
            continue
        if entry.get("first_seen", today) < cutoff:
            new_state.pop(app_id, None)

    if len(new_state) > CHART_MAX_TRACKED_APPS:
        evictable = sorted(new_state.keys(), key=lambda aid: new_state[aid].get("first_seen", today))
        for aid in evictable[:len(new_state) - CHART_MAX_TRACKED_APPS]:
            new_state.pop(aid, None)

    return newly_free, new_state


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


# Palette read directly off a real screenshot of the actual product (light
# theme: white background, near-black text, a clean blue used specifically
# for buttons/links/active-states, and a separate green used specifically
# for status pills like their "OK" badges) - an earlier version of this
# guessed dark-mode-with-lime-accent from search-result thumbnails, which
# turned out backwards on both counts. Kept as named constants so this
# stays easy to retune if it needs correcting again.
BG = "#F7F8FA"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E5E7EB"
TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#6B7280"
ACCENT = "#3B5BDB"       # buttons, links, active states - matches their "Run now" blue
ACCENT_TEXT = "#FFFFFF"  # text on top of a solid ACCENT fill
STAR_COLOR = "#F5A623"   # star ratings stay amber/gold regardless of brand color - near-universal convention
SUCCESS_BG = "#DCFCE7"   # status pill background, matches their green "OK" badges
SUCCESS_TEXT = "#15803D"  # status pill text


def source_tag_html(source):
    return f"<span style=\"color:{TEXT_SECONDARY};font-size:11px;text-transform:uppercase;letter-spacing:.04em;\">via {escape(source)}</span>"


def render_app_card_html(app, card_style_extra=""):
    """Renders one app as a card - shared by the real email (build_html)
    and the standalone preview page, so the card itself (icon/name/price/
    source) can never drift between the two. Only the page chrome around
    it differs."""
    rating_html = ""
    if app.get("rating"):
        rating_html = (
            f"<span style='color:{STAR_COLOR}'>{escape(star_string(app['rating']))}</span> "
            f"<span style='color:{TEXT_SECONDARY}'>{app['rating']:.1f} ({app.get('rating_count', 0):,})</span>"
        )
    icon_html = (
        f"<img src='{escape(app['icon'])}' width='64' height='64' "
        f"style='border-radius:16px;display:block' alt=''>"
        if app.get("icon") else ""
    )
    badge, badge_sub = price_badge(app["price_label"])
    genre_bits = " · ".join(x for x in [app.get("developer", ""), app.get("genre", "")] if x)
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;max-width:680px;margin:0 0 16px;background:{CARD_BG};border:1px solid {CARD_BORDER};border-radius:14px;box-shadow:0 1px 2px rgba(16,24,40,0.04);{card_style_extra}">
  <tr>
    <td style="width:88px;padding:20px 0 20px 20px;vertical-align:top;">{icon_html}</td>
    <td style="padding:20px;vertical-align:top;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
      <div style="font-size:16px;font-weight:700;letter-spacing:-.01em;">
        <a href="{escape(app['url'])}" style="color:{TEXT_PRIMARY};text-decoration:none;">{escape(app['name'])}</a>
      </div>
      <div style="font-size:13px;color:{TEXT_SECONDARY};margin:4px 0 8px;">{escape(genre_bits)}</div>
      <div style="font-size:13px;margin-bottom:8px;">{rating_html}</div>
      <div style="font-size:13px;color:{TEXT_SECONDARY};line-height:1.5;">{escape(truncate(app.get('description', '')))}</div>
      <div style="margin-top:14px;">
        <span style="background:{SUCCESS_BG};color:{SUCCESS_TEXT};font-weight:600;padding:3px 10px;border-radius:6px;font-size:12px;">{badge}</span>
        <span style="color:{TEXT_SECONDARY};margin-left:8px;font-size:12px;">{escape(badge_sub)}</span>
        <span style="float:right;">{source_tag_html(app.get('source', ''))}</span>
      </div>
    </td>
  </tr>
</table>"""


def build_html(new_apps, timestamp, stats):
    if not new_apps:
        cards = f"<p style='color:{TEXT_SECONDARY};font-size:14px;'>Nothing new since the last check.</p>"
    else:
        cards = "\n".join(render_app_card_html(app) for app in new_apps)

    return f"""\
<html>
<head><meta name="color-scheme" content="light"></head>
<body style="margin:0; padding:32px 20px; background:{BG}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;max-width:720px;margin:0 auto;">
    <tr><td>
      <h1 style="color:{TEXT_PRIMARY};font-size:28px;font-weight:800;letter-spacing:-.02em;margin:0 0 8px;">iOS Apps Gone Free</h1>
      <p style="color:{TEXT_SECONDARY};font-size:14px;margin:0 0 24px;">Checked {escape(timestamp)} &middot; {stats.get('scraped', 0)} from iGeeksBlog/AppDovo + {stats.get('chart', 0)} from Apple's top-paid chart &middot; {stats['new']} new &middot; {stats['repeat']} already sent within the last {COOLDOWN_DAYS} days</p>
      {cards}
      <p style="color:{TEXT_SECONDARY}; font-size:12px; line-height:1.6; margin-top:28px;">
        Sources: <a href="{escape(IGEEKSBLOG_URL)}" style="color:{ACCENT};">iGeeksBlog</a> and
        <a href="{escape(APPDOVO_URL)}" style="color:{ACCENT};">AppDovo</a> (both hand-curated/scraped) and
        Apple's own top-paid chart feed (auto-discovered, tracked for price drops) &middot;
        all cross-checked against Apple's iTunes Lookup API (country={escape(COUNTRY)}) &middot; "FREE+" means
        the app itself was already free to download and a premium/subscription tier has been unlocked for now,
        not that the whole app was a paid download &middot; Promotions can end at any time - check the App Store
        link before assuming it's still free.
      </p>
    </td></tr>
  </table>
</body>
</html>"""


def build_plain_text(new_apps, timestamp, stats):
    lines = [
        f"iOS Apps Gone Free - checked {timestamp}",
        f"{stats.get('scraped', 0)} from iGeeksBlog/AppDovo + {stats.get('chart', 0)} from Apple's top-paid chart, "
        f"{stats['new']} new, {stats['repeat']} already sent within the last {COOLDOWN_DAYS} days",
        "",
    ]
    if not new_apps:
        lines.append("Nothing new since the last check.")
    else:
        for app in new_apps:
            badge, badge_sub = price_badge(app["price_label"])
            lines.append(f"- {app['name']} ({badge} - {badge_sub}) [via {app.get('source', '?')}]")
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


def build_preview_page_html(new_apps, timestamp, stats):
    """A standalone preview webpage - icon sidebar + top search bar + main
    content area, modeled on a real screenshot of the actual product (an
    app-shell layout, not a marketing landing page - that was the wrong
    reference the first time around). This is NOT what gets emailed (see
    build_html() for that, which stays a plain, conservative wrapper for
    email-client compatibility) - it's a nicer way to browse the same
    underlying cards in an actual browser. The cards themselves come from
    the exact same render_app_card_html() the real email uses, so what
    you see here is never cosmetically different from what would actually
    be emailed - only the chrome around it is."""
    if new_apps:
        card_grid = "\n".join(
            f'<div style="break-inside:avoid;margin-bottom:16px;">{render_app_card_html(app)}</div>'
            for app in new_apps
        )
    else:
        card_grid = f"<p style='color:{TEXT_SECONDARY};font-size:14px;'>Nothing new since the last check.</p>"

    stat_cards = "".join(f"""
    <div style="background:{CARD_BG};border:1px solid {CARD_BORDER};border-radius:12px;padding:16px 20px;flex:1;min-width:130px;">
      <div style="font-size:26px;font-weight:700;color:{TEXT_PRIMARY};letter-spacing:-.02em;">{value}</div>
      <div style="font-size:12px;color:{TEXT_SECONDARY};margin-top:2px;">{label}</div>
    </div>""" for value, label in [
        (stats["new"], "New today"),
        (stats.get("scraped", 0), "From iGeeksBlog/AppDovo"),
        (stats.get("chart", 0), "From Apple charts"),
        (f"{COOLDOWN_DAYS}d", "Repeat cooldown"),
    ])

    sidebar_icons = "".join(f"""
    <div style="display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 8px;border-radius:10px;{'background:#EEF1FF;color:' + ACCENT if active else 'color:' + TEXT_SECONDARY};">
      <div style="font-size:18px;line-height:1;">{icon}</div>
      <div style="font-size:10px;">{label}</div>
    </div>""" for icon, label, active in [
        ("&#8962;", "Home", False), ("&#128229;", "Digest", True),
        ("&#128279;", "Sources", False), ("&#9881;", "Settings", False),
    ])

    return f"""\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iOS Apps Gone Free - Preview</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:{BG}; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif; color:{TEXT_PRIMARY}; }}
  .shell {{ display:flex; min-height:100vh; }}
  .sidebar {{ width:76px; background:{CARD_BG}; border-right:1px solid {CARD_BORDER}; padding:16px 8px; display:flex; flex-direction:column; align-items:center; gap:6px; flex-shrink:0; }}
  .sidebar-logo {{ width:32px; height:32px; border-radius:8px; background:{ACCENT}; color:{ACCENT_TEXT}; display:flex; align-items:center; justify-content:center; font-weight:800; margin-bottom:12px; }}
  .main {{ flex:1; min-width:0; }}
  .topbar {{ display:flex; align-items:center; justify-content:space-between; padding:14px 28px; background:{CARD_BG}; border-bottom:1px solid {CARD_BORDER}; }}
  .topbar-brand {{ display:flex; align-items:center; gap:10px; font-weight:800; font-size:15px; }}
  .search {{ flex:1; max-width:420px; margin:0 24px; padding:9px 14px; background:{BG}; border:1px solid {CARD_BORDER}; border-radius:8px; color:{TEXT_SECONDARY}; font-size:13px; display:flex; justify-content:space-between; }}
  .topbar-badge {{ background:{SUCCESS_BG}; color:{SUCCESS_TEXT}; font-weight:700; font-size:11px; padding:4px 10px; border-radius:6px; }}
  .content {{ max-width:900px; margin:0 auto; padding:32px 28px 56px; }}
  .content h1 {{ font-size:24px; font-weight:700; letter-spacing:-.02em; margin:0 0 6px; }}
  .content > p {{ color:{TEXT_SECONDARY}; font-size:14px; margin:0 0 24px; }}
  .stats-row {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:32px; }}
  .grid {{ column-count:2; column-gap:16px; }}
  @media (max-width:720px) {{ .grid {{ column-count:1; }} .sidebar {{ display:none; }} .search {{ display:none; }} }}
  .footer {{ max-width:900px; margin:0 auto; padding:24px 28px 0; color:{TEXT_SECONDARY}; font-size:12px; line-height:1.6; border-top:1px solid {CARD_BORDER}; margin-top:8px; }}
  .footer a {{ color:{ACCENT}; }}
</style>
</head>
<body>
  <div class="shell">
    <div class="sidebar">
      <div class="sidebar-logo">A</div>
      {sidebar_icons}
    </div>
    <div class="main">
      <div class="topbar">
        <div class="topbar-brand">Apps Gone Free</div>
        <div class="search"><span>Search apps...</span><span>&#8984;K</span></div>
        <div class="topbar-badge">PREVIEW</div>
      </div>
      <div class="content">
        <h1>Today's digest</h1>
        <p>Checked {escape(timestamp)} &middot; {stats['new']} new since the last check, {stats['repeat']} already sent within the last {COOLDOWN_DAYS} days.</p>
        <div class="stats-row">{stat_cards}</div>
        <div class="grid">{card_grid}</div>
        <div class="footer">
          This is a local preview generated by <code>python apps_gone_free_emailer.py preview</code> from
          sample data - not a real digest. The cards above use the exact same rendering as the real email;
          only this sidebar/topbar chrome is preview-only, since actual emails don't have navigation. Sources:
          <a href="{escape(IGEEKSBLOG_URL)}">iGeeksBlog</a>, <a href="{escape(APPDOVO_URL)}">AppDovo</a>, and
          Apple's top-paid chart feed, all cross-checked against Apple's iTunes Lookup API.
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""


def resolve_timestamp():
    timezone_name = os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh")
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.now()
    return now, now.strftime("%H:%M %d/%m/%Y")


# --- Icon rehosting (mirrors 9gag-meme-emailer's asset-publishing pattern) -
#
# App icons already come from Apple's own CDN (mzstatic.com), which is
# built for exactly this kind of external hotlinking - unlike a source
# where rehosting solves a real problem, this is being done for
# consistency with the rest of this project family rather than necessity.
# See README for that discussion. Mirrors the shape exactly: download to a
# local directory, the workflow publishes that directory to a dedicated
# branch and waits for raw.githubusercontent.com to catch up, then the
# email is sent referencing the new URLs.

ICON_ASSETS_DIR = os.environ.get("ICON_ASSETS_DIR", "")  # set by the workflow; empty = rehosting disabled
ICON_ASSETS_BRANCH = os.environ.get("ICON_ASSETS_BRANCH", "icon-assets")


def rehost_icons(apps):
    """Downloads each app's icon into ICON_ASSETS_DIR and rewrites
    app['icon'] to the future raw.githubusercontent.com URL a workflow
    step will publish it to. No-ops (leaves the original CDN URL alone)
    unless both ICON_ASSETS_DIR and GITHUB_REPOSITORY (set automatically
    by GitHub Actions) are present - so local runs and `preview` are
    unaffected and keep making zero network calls beyond what they
    already did. Tolerant of individual download failures - falls back
    to the original CDN URL for that one app rather than breaking the
    whole run over one bad icon fetch."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not ICON_ASSETS_DIR or not repo:
        return apps
    os.makedirs(ICON_ASSETS_DIR, exist_ok=True)
    for app in apps:
        if not app.get("icon"):
            continue
        try:
            resp = http_get(app["icon"])
            ext = os.path.splitext(app["icon"].split("?")[0])[1] or ".png"
            filename = f"{app['id']}{ext}"
            with open(os.path.join(ICON_ASSETS_DIR, filename), "wb") as f:
                f.write(resp.content)
            app["icon"] = f"https://raw.githubusercontent.com/{repo}/{ICON_ASSETS_BRANCH}/{filename}"
        except requests.RequestException as e:
            print(f"  couldn't rehost icon for {app['name']!r}: {e} - leaving original CDN URL", file=sys.stderr)
    return apps


# --- Commands -----------------------------------------------------------

def cmd_generate():
    print(f"apps_gone_free_emailer.py version: {SCRIPT_VERSION}")
    if os.path.exists(EMAIL_DIR):
        for f in os.listdir(EMAIL_DIR):
            os.remove(os.path.join(EMAIL_DIR, f))
    os.makedirs(EMAIL_DIR, exist_ok=True)

    old_state = load_state()
    old_chart_state = load_state(CHART_STATE_FILE)

    print("Fetching source(s) ...")
    scraped = fetch_all_sources()
    print(f"  {len(scraped)} app(s) total after merging scraped sources.")
    verified = enrich_and_verify(scraped) if scraped else []
    if scraped:
        print(f"  {len(verified)}/{len(scraped)} app(s) kept after cross-check.")

    print(f"Checking Apple's top-paid chart (country={COUNTRY}) ...")
    chart_new, new_chart_state = discover_chart_gone_free(old_chart_state)
    print(f"  {len(chart_new)} app(s) newly free via the chart.")
    save_state(new_chart_state, CHART_STATE_FILE)  # save regardless of whether an email goes out

    combined = verified + chart_new
    if not scraped and not new_chart_state:
        # Every scraped site (iGeeksBlog, AppDovo) came back with nothing AND
        # the chart source has never successfully tracked a single
        # candidate (this run's chart fetch failed with no prior state to
        # fall back on either). That's a real problem worth flagging
        # loudly, distinct from "nothing NEW today" (normal, most days,
        # handled further down) - don't touch state.
        print("Every source found 0 apps this run - probably a scraper/markup or API problem, "
              "not a quiet day. Aborting without sending or touching the notified-apps state.",
              file=sys.stderr)
        with open(os.path.join(EMAIL_DIR, "meta.json"), "w") as f:
            json.dump({"send": False, "scraped": 0, "chart": 0, "new": 0, "repeat": 0}, f)
        return

    new_apps, repeat_apps = split_new_and_repeat(combined, old_state)
    stats = {"scraped": len(verified), "chart": len(chart_new), "new": len(new_apps), "repeat": len(repeat_apps)}
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

    rehost_icons(new_apps)  # no-op outside GitHub Actions - see function docstring
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


def cmd_preview():
    """Generates preview.html (a full sidebar/topbar/grid webpage, see
    build_preview_page_html()) and preview.txt (build_plain_text(), same
    as a real email) from sample data. The individual app cards on
    preview.html come from render_app_card_html() - the exact same
    function build_html() uses for real emails - so a card can never look
    cosmetically different here than it would in an actual email; only
    the surrounding sidebar/topbar/grid chrome is preview-only, since real
    emails don't have navigation bars. Sample apps mix all three sources
    and both price labels on purpose, to show the visual variety a real
    digest can have. Doesn't touch state, doesn't send anything, doesn't
    hit the network."""
    sample_apps = [
        {
            "id": "6785703404", "name": "ASABlocker", "developer": "Solo Dev",
            "icon": "https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/2b/4d/3e/2b4d3e28-51d1-9eb7-b39e-d6e0fdd345a9/Placeholder.mill/200x200bb-75.png",
            "url": "https://apps.apple.com/app/id6785703404", "genre": "Utilities",
            "rating": 4.2, "rating_count": 340,
            "description": "Blocks Apple Search Ads from cluttering App Store search results.",
            "price_label": "Free", "source": "iGeeksBlog",
        },
        {
            "id": "6785424413", "name": "Authenticator App Vault+", "developer": "Vault Labs",
            "icon": "https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/4e/ea/cc/4eeacccf-446f-c8c6-cfff-9ceb298a1399/Placeholder.mill/200x200bb-75.png",
            "url": "https://apps.apple.com/app/id6785424413", "genre": "Utilities",
            "rating": 4.7, "rating_count": 2103,
            "description": "Two-factor authenticator with iCloud sync and Face ID lock.",
            "price_label": "Free+", "source": "iGeeksBlog",
        },
        {
            "id": "6789931132", "name": "VRAMFit: LLM Calculator", "developer": "VRAMFit",
            "icon": "https://is1-ssl.mzstatic.com/image/thumb/PurpleSource211/v4/1b/90/92/1b909286-d073-1d96-2f47-7d0e093ec1af/Placeholder.mill/200x200bb-75.png",
            "url": "https://apps.apple.com/app/id6789931132", "genre": "Developer Tools",
            "rating": 4.9, "rating_count": 87,
            "description": "Estimates GPU memory needed to run a given LLM locally.",
            "price_label": "Free+", "source": "iGeeksBlog",
        },
        {
            "id": "6774355361", "name": "NeonVortex", "developer": "Jeff Curtis",
            "icon": "https://appdovo.com/wp-content/uploads/2026/08/6774355361AppIcon-0-0-1x_pad-300x300.jpg",
            "url": "https://apps.apple.com/app/id6774355361", "genre": "Music",
            "rating": 4.6, "rating_count": 512,
            "description": "A visual music player with reactive neon animations synced to your library.",
            "price_label": "Free", "source": "AppDovo",
        },
        {
            "id": "0000000001", "name": "[SAMPLE] Focus Timer Pro", "developer": "Placeholder Co",
            "icon": "", "url": "https://apps.apple.com/app/id0000000001", "genre": "Productivity",
            "rating": 4.8, "rating_count": 15420,
            "description": "Not a real listing - placeholder data to show how a chart-discovered "
                            "app (no icon guaranteed, since this source has no scraped image) renders.",
            "price_label": "Free", "source": "Apple Top-Paid Chart",
        },
    ]
    # Computed from sample_apps itself rather than hardcoded - a hardcoded
    # count is exactly how the missing AppDovo example above went unnoticed
    # when that source was added.
    scraped_count = sum(1 for a in sample_apps if a["source"] != "Apple Top-Paid Chart")
    chart_count = sum(1 for a in sample_apps if a["source"] == "Apple Top-Paid Chart")
    stats = {"scraped": scraped_count, "chart": chart_count, "new": len(sample_apps), "repeat": 2}
    _, timestamp = resolve_timestamp()
    html = build_preview_page_html(sample_apps, timestamp, stats)
    text = build_plain_text(sample_apps, timestamp, stats)
    with open("preview.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("preview.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Wrote preview.html and preview.txt (sample data, no state touched, nothing sent/scraped).")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("generate", "send", "preview"):
        print("Usage: python apps_gone_free_emailer.py [generate|send|preview]", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "generate":
        cmd_generate()
    elif sys.argv[1] == "send":
        cmd_send()
    else:
        cmd_preview()


if __name__ == "__main__":
    main()
