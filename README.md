# iOS Apps Gone Free Emailer (runs on GitHub Actions, no local computer needed)

Emails you a digest of iOS apps that have gone free today, automatically,
via GitHub's free scheduled-workflow runners.

Modeled on [tech-price-mailer](https://github.com/tuongphantrue/tech-price-mailer) and
[currency-rate-emailer](https://github.com/tuongphantrue/currency-rate-emailer) -
same generate/send two-phase shape, same Gmail-SMTP delivery, same
dedup-via-state-branch trick.

## Important: read this before relying on it

[#important-read-this-before-relying-on-it](#important-read-this-before-relying-on-it)

A lot of the sites people remember for this have quietly died. Three
rounds of checking what's actually still alive in 2026:

| Site | Status |
| --- | --- |
| AppShopper.com | Shut down 2021-06-30. |
| iOSnoops.com | Was still posting in 2023; its own homepage now just says "we have decided to shut down the site." |
| AppAdvice.com "Apps Gone Free" | Stopped being updated in early 2026. Page still online but frozen on a mid-January 2026 post. |
| AppRaven (appraven.net) | Active, but pure client-side JS - no server-rendered HTML for a plain scraper to read. |
| AppSliced.co | Now just redirects to AppRaven - same dead end. |
| AppsHunter.io, 148apps.com | Active, but general app catalogs / gaming-news sites, not a clean "gone free today" list. |
| AppStore-Discounts.com | Would've been ideal - 770K+ apps, hourly refresh via Apple's own API, explicitly tracks apps hitting 100% free - but its `robots.txt` disallows automated access. Skipped on principle. |
| PSprices.com | Has an RSS feed and clean pages, but turns out to be a console/PC gaming price tracker (PlayStation, Xbox, Switch) with iOS as a minor secondary platform - wrong scope. |
| Reddit r/AppHookup | Active (204k members), and individual posts do follow a `[iOS] [App] [$X → Free]` bracket convention - but it mixes multi-day roundup posts with individual ones, spans many platforms, and reliable JSON API access without auth is genuinely uncertain in 2026. Didn't clear the bar to ship. |
| Yitake.in | Has a "Today's Apps Gone Free" page, but the content reads as templated/AI-generated filler rather than genuinely curated - passed on quality grounds. |
| **iGeeksBlog.com** | **Active, updated daily** - one bookmarkable page it edits in place. |
| **AppDovo.com** | **Active, recently-updated content** - a mixed iOS+Android, free+discounted deals feed. See below for how this one's integrated and its one real caveat. |

Given how thin that list is, this doesn't rely on any one site alone -
it runs **three independent sources** and merges whatever any of them
find:

1. **iGeeksBlog scrape** - the hand-curated list above, the same way
   tech-price-mailer scrapes MemoryZone.vn. Every app it finds is
   cross-checked against Apple's own iTunes Lookup API - a plain
   "Free" listing (was a normal paid download, now $0) that no longer
   shows $0.00 there gets dropped as stale rather than emailed.
   "Free+" listings (already free to download, with a premium tier
   unlocked for now) can't be verified the same way, since a free
   download always shows $0.00 regardless - those go out on
   iGeeksBlog's own editorial word.
2. **AppDovo scrape** - mixes iOS/Android and free/merely-discounted
   deals in one list, filtered here to iOS + exactly 100% off. Worth
   knowing the one real caveat: this listing page's own links go to
   AppDovo's site, not the App Store, so there's no `apps.apple.com`
   link to read a certain id from the way there is on iGeeksBlog.
   `parse_appdovo()` instead reads a leading digit run AppDovo embeds
   in its own cached icon filenames (e.g.
   `.../6774355361AppIcon-....jpg`), which matches Apple's id format
   closely enough to be a reasonable bet - but it's a bet, not a
   certainty. Because of that, AppDovo entries go through a stricter
   check than iGeeksBlog's: the guessed id has to resolve via iTunes
   Lookup *and* the looked-up name has to reasonably match what was
   scraped, or the entry gets dropped rather than risking a broken or
   mismatched link (see `SOURCES_WITH_CERTAIN_IDS` /
   `enrich_and_verify()`). Verified against a fixture built from
   AppDovo's real fetched content, but not against raw HTML the way
   iGeeksBlog eventually was - same debug-artifact safety net applies
   if the real markup turns out to disagree.
3. **Apple's own top-paid chart feed** - auto-discovers popular paid
   apps directly from Apple (`rss.applemarketingtools.com`, no
   scraping involved at all), remembers each one's price between runs,
   and reports any that drop to $0.00. Structurally immune to the kind
   of HTML/markup breakage that hit the scrapers repeatedly while this
   was being built - there's no page to change.

The three sources have different blind spots on purpose: iGeeksBlog and
AppDovo each catch apps a human/algorithm bothered to feature that the
other might not; the chart catches popular apps regardless of whether
any site ever wrote about them. Any one (or two) failing - site down,
markup changed, Apple's API having a bad day - no longer means an empty
inbox, as long as at least one source still comes through - see "Every
source found 0 apps this run" in Troubleshooting for the case where none do.

This is a personal notification tool, not a guarantee of catching every
app that goes free, and not purchase advice - always check the App
Store link before assuming something is still free, promos can end
anytime.

## One-time setup (~5 minutes)

[#one-time-setup-5-minutes](#one-time-setup-5-minutes)

1. **Create a GitHub account** if you don't have one: <https://github.com/join>

2. **Create a new repository**

   - Click "+" (top right) -> "New repository"
   - Name it anything, e.g. `apps-gone-free-emailer`
   - Set it to **Private** (recommended, keeps your workflow config private)
   - Click "Create repository"

3. **Upload these files** to the repo (drag-and-drop works fine via the
   GitHub web UI: "Add file" -> "Upload files"), keeping the folder structure:

   - `apps_gone_free_emailer.py`
   - `requirements.txt`
   - `.github/workflows/send-apps-gone-free.yml`

4. **Create a Gmail "App Password"** (your normal Gmail password won't work):

   - Turn on 2-Step Verification: <https://myaccount.google.com/signinoptions/two-step-verification>
   - Then create an app password: <https://myaccount.google.com/apppasswords>
   - Choose "Mail" as the app, copy the 16-character password it gives you.

5. **Add your secrets to the repo** (this keeps your email/password out of the code):

   - In your repo: Settings -> Secrets and variables -> Actions -> "New repository secret"
   - Add three secrets:
     - `GMAIL_ADDRESS` = your Gmail address
     - `GMAIL_APP_PASSWORD` = the 16-character app password from step 4
     - `APPS_RECIPIENT` = the email address that should receive the digest

6. **Test it manually**

   - Go to the "Actions" tab in your repo
   - Click "Send iOS Apps Gone Free Email" on the left
   - Click "Run workflow" -> "Run workflow" (green button)
   - Wait ~15-20 seconds, refresh, click into the run to see logs / confirm success
   - Check the recipient inbox for the email (the first run will only
     email if there's something new to report - see "Avoiding duplicate
     emails" below for why a quiet first run is normal)

That's it - from now on it runs automatically on the schedule below.

## Changing the schedule

[#changing-the-schedule](#changing-the-schedule)

Open `.github/workflows/send-apps-gone-free.yml` and edit this line:

```
- cron: "*/30 * * * *"
```

Cron format is `minute hour day month weekday`, always in **UTC**.

- `*/30 * * * *` -> every 30 minutes - current setting
- `0 1 * * *` -> once a day at 1am UTC (8am Vietnam, UTC+7)
- `0 1,13 * * *` -> twice a day, 1am and 1pm UTC
- `0 */6 * * *` -> every 6 hours

iGeeksBlog updates that page roughly daily, so at `*/30 * * * *` most of
the ~48 runs/day will find nothing new and send no email - the dedup
state means you won't get repeat emails about the same app. Two things
worth knowing about running it this often, purely as information, not a
suggestion to change it: it's about 48x more requests against a small
site's server than the content needs, and it uses noticeably more of
your Actions minutes (private repos get 2,000 free/month; 48 runs/day is
roughly 1,000-1,500+ minutes/month depending on how long each run takes,
versus well under 100/month at once a day). Mentioning it once here in
case it's useful later - the schedule line itself is yours to keep.

## Avoiding duplicate emails (cooldown)

[#avoiding-duplicate-emails-cooldown](#avoiding-duplicate-emails-cooldown)

An app that goes free often stays listed for a day or two before
reverting, and this workflow can run more than once a day - without any
dedup you'd get the same app re-emailed every single run it's still
listed. To avoid that, every app that goes out in an email gets recorded
(with today's date) in `STATE_FILE`, stored on a dedicated `apps-state`
branch the workflow creates/updates automatically (same trick as
tech-price-mailer's `state/last_price.json` on its own branch). An app
already recorded within the last `COOLDOWN_DAYS` (default 21) is treated
as a repeat and left out of the email, even if iGeeksBlog is still
listing it. If it goes free again after a longer gap, it's treated as
news again.

This also means the very first run behaves a bit differently: with no
prior state at all, everything iGeeksBlog currently lists counts as
"new" and goes out immediately, even if some of it had already been up
for a day or two before you set this up. It's the runs *after* that
where the cooldown kicks in and quiet days become genuinely quiet (no
email at all, unless `ALWAYS_SEND=true`).

## Configuration

[#configuration](#configuration)

These are optional environment variables you can add to the "Generate
email" step in the workflow (or export locally):

```
COUNTRY: "us"                        # App Store storefront for both sources
COOLDOWN_DAYS: "21"                  # don't re-email the same app within this many days
ALWAYS_SEND: "false"                 # "true" = still send a "nothing new" email every run
TIMEZONE: "Asia/Ho_Chi_Minh"         # only affects the timestamp shown in the email
STATE_FILE: "state/notified.json"    # dedup state file path
IGEEKSBLOG_URL: "https://www.igeeksblog.com/paid-iphone-apps-gone-free/"
APPDOVO_URL: "https://appdovo.com/apps-gone-free-today/"
ALLOW_INSECURE_SSL_FALLBACK: "false" # last-resort TLS bypass

# Apple top-paid chart source
CHART_LIMIT: "100"                        # apps to pull from the chart per run (informal ceiling as of 2026)
CHART_STATE_FILE: "state/chart_candidates.json"  # separate state file - price history for chart-discovered apps
CHART_MAX_TRACK_AGE_DAYS: "21"            # stop watching a chart candidate after this long if it never goes free
CHART_MAX_TRACKED_APPS: "2000"            # hard cap on the chart candidate state file's size
CHART_FETCH_RETRIES: "3"                  # retries per limit on transient network errors (timeouts etc.)
CHART_FETCH_RETRY_DELAY: "5"              # seconds between those retries

# Icon rehosting (see "Icon hosting" below - only activates inside GitHub Actions)
ICON_ASSETS_DIR: ""      # local dir to save downloaded icons into; empty (default) = rehosting disabled
ICON_ASSETS_BRANCH: "icon-assets"  # branch icons get published to
```

## Adding another source

[#adding-another-source](#adding-another-source)

Two different extension points, depending on what you find:

- **Another scraped listing site**: `SOURCES` near the top of
  `apps_gone_free_emailer.py` is a list of `{"name", "url", "parser"}` -
  iGeeksBlog and AppDovo currently. `fetch_all_sources()` already
  fetches every entry in that list, tolerates any one of them failing,
  and dedupes apps by App Store id across sources. Write a
  `parse_<site>(html) -> [{"id", "name", "icon", "url", "price_label"}, ...]`
  function (see `parse_igeeksblog()` for the shape, or `parse_appdovo()`
  if the site doesn't link directly to the App Store) and append it to
  `SOURCES`. If the site's own links go straight to `apps.apple.com`,
  add its name to `SOURCES_WITH_CERTAIN_IDS` too; if the id has to be
  inferred some other way, leave it out so `enrich_and_verify()` applies
  the stricter identity check instead. Worth grabbing real page source
  (view-source, not a text/markdown rendering of it) before writing the
  parser - see "Troubleshooting" below for exactly why that distinction
  mattered here.
- **Another official API, same shape as the chart source**: if you find
  another store's or service's own public API worth tracking the same
  way (auto-discover candidates, remember prices, report drops to $0),
  `discover_chart_gone_free()` is the pattern to copy - it's independent
  of `SOURCES` entirely and merges into `cmd_generate()` alongside it.

## Visual design

[#visual-design](#visual-design)

Modeled on rework.com's actual UI - a **light** theme (white/near-white
background, near-black text) with a clean **blue** accent (`#3B5BDB`)
used specifically for buttons/links/active states, and a separate
**green** used specifically for status pills (their "OK" badges - this
project's "FREE" badge borrows that same pattern). Named constants
`BG`, `CARD_BG`, `ACCENT`, `SUCCESS_BG`, etc. near the top of the file,
easy to retune in one place.

Worth being honest about how this got nailed down: rework.com is a
JS-only SPA with no server-rendered markup to read exact values from,
so the first attempt was built from search-result thumbnails and got
it backwards on both counts - guessed a dark background with a bright
lime accent. It took an actual screenshot of the real product (a
logged-in settings page, not the marketing site) to see the real
pattern: light theme, blue for interactive elements, green reserved for
status. If this is ever off again, a real screenshot is a much faster
way to fix it than another round of image search.

There are two templates, on purpose:

- **`build_html()`** - what actually gets emailed. Stays a plain
  wrapper (title, stats line, cards, footer) with no nav/sidebar chrome,
  because it has to survive being rendered by Gmail/Outlook/etc., which
  don't reliably support modern CSS.
- **`build_preview_page_html()`** - what `preview.html` uses. A fuller
  app-shell UI - icon sidebar, top search bar, dashboard-style stat
  cards, a responsive two-column grid - since a browser has none of an
  email client's constraints. Individual app cards come from the shared
  `render_app_card_html()`, the same function `build_html()` uses, so
  the cards themselves are guaranteed identical between the two - only
  the surrounding chrome (sidebar/topbar/grid vs. plain stack) differs.

## Icon hosting

[#icon-hosting](#icon-hosting)

Worth being upfront about this one, since it's the one piece here that
isn't solving a problem this project actually has.

App icons come from Apple's own CDN (`mzstatic.com`), which is built
for exactly this kind of external hotlinking - it's what every app
review site and App Store link preview on the web already does. Left
alone, that's already reliable.

This project's sibling, [9gag-meme-emailer](https://github.com/tuongphantrue/9gag-meme-emailer),
downloads its images and republishes them to a dedicated `meme-assets`
branch, served back out via `raw.githubusercontent.com`, because *its*
source images aren't something you can reliably hotlink long-term. That
specific problem doesn't apply to Apple's icon CDN. This project adopts
the same pattern anyway, by explicit choice, for consistency with the
rest of the project family rather than necessity - noting that
up front so it doesn't read as if rehosting were fixing something that
was actually broken.

**How it works:** `rehost_icons()` in `apps_gone_free_emailer.py`
downloads each newly-free app's icon into `ICON_ASSETS_DIR` and rewrites
its URL to the future `raw.githubusercontent.com` location. The
workflow's **"Publish images to the icon-assets branch"** step then
pushes that directory to a dedicated `icon-assets` branch - same
git-worktree trick as the dedup-state branch, tested to correctly
*accumulate* icons across runs rather than overwrite them (unlike
state, old emails still need their images to keep resolving later) -
and **"Wait for raw.githubusercontent.com to serve the new files"**
gives the CDN ~30s to catch up before the email actually sends.

**A real trade-off worth knowing about:** unlike the dedup-state file,
icons are never pruned - every unique app icon ever emailed stays in
that branch forever, since deleting one could break the image in an
already-delivered email if the recipient's mail client re-fetches
remote images on every open rather than caching at delivery time (this
varies by client). Icons are small (a few KB each at the size used
here) and this only downloads new ones on days something's actually
newly free, so growth should stay modest in practice - but if it's ever
worth bounding, `ICON_ASSETS_DIR` / `ICON_ASSETS_BRANCH` are both
configurable, and a time-based prune of the branch is the natural place
to add it later.

Both `ICON_ASSETS_DIR` and `GITHUB_REPOSITORY` (set automatically by
GitHub Actions) have to be present for any of this to activate -
running `generate` locally or `preview` never downloads or rewrites
icons, so both keep their existing "no surprise network calls" behavior
unchanged.

## Notes

[#notes](#notes)

- The workflow needs write access to push its dedup state branch. It
  requests this itself (`permissions: contents: write` at the top of
  `send-apps-gone-free.yml`), but some accounts/orgs override that and
  force the token to read-only regardless. If the "Persist dedup state
  to state branch" step fails with `403` / `Permission ... denied`, go
  to **Settings -> Actions -> General -> Workflow permissions** in your
  repo and select **"Read and write permissions"**, then re-run the
  workflow.
- Every `generate` run prints `apps_gone_free_emailer.py version: ...`
  as its very first log line (`SCRIPT_VERSION` near the top of the
  file, bumped whenever the parser/heading logic changes meaningfully).
  If something's misbehaving and you're not sure whether the fix you
  just applied actually made it into the run, this is the fast way to
  check without diffing file contents by hand.
- GitHub Actions free tier includes 2,000 minutes/month for private repos.
- You can also trigger it manually anytime via the "Run workflow" button.
- Worth checking iGeeksBlog's current `robots.txt` / terms before
  running this unattended long-term: <https://www.igeeksblog.com/robots.txt>
- This tool isn't affiliated with iGeeksBlog or Apple; it just reads a
  public page and a public Apple API. Please don't crank the schedule up
  to something aggressive (e.g. every few minutes) against a small site's
  server for a page that only changes about once a day.
- This is a personal notification tool, not investment or purchase advice.

### Troubleshooting: a run logs "Every source found 0 apps this run"

[#troubleshooting-a-run-logs-every-source-found-0-apps-this-run](#troubleshooting-a-run-logs-every-source-found-0-apps-this-run)

This is the only case where nothing gets emailed *and* state is left
untouched entirely - every scraped site (iGeeksBlog and AppDovo both)
and the chart discovery all came back with genuinely nothing, not just
nothing new. Three independent things would all have to be broken at
once for this to fire, so it's worth checking the log for which one(s)
actually failed: each scraped site logs its own reason (see below), and
the chart source logs `chart fetch at limit=N failed: ...` if
`rss.applemarketingtools.com` itself is unreachable or erroring - now
with a few automatic retries first (see "Chart API reliability" below)
before it actually gives up.

### Chart API reliability, and why a log's line order can look wrong

[#chart-api-reliability-and-why-a-logs-line-order-can-look-wrong](#chart-api-reliability-and-why-a-logs-line-order-can-look-wrong)

Two small things worth knowing about, both prompted by the same real
run's log:

- **A single timeout used to be fatal for the chart source.**
  `fetch_top_paid_ids()` retries with `CHART_FALLBACK_LIMIT` if the
  *requested* limit gets rejected - but when the limit is already the
  default (100, same as the fallback), that loop only ever ran once, so
  a single transient timeout had zero cushion. It now separately retries
  `CHART_FETCH_RETRIES` times (default 3, `CHART_FETCH_RETRY_DELAY`
  seconds apart) on network errors specifically, independent of the
  limit-fallback logic, which exists for a different failure mode
  entirely (the endpoint rejecting an oversized limit, not the network
  being flaky).
- **A confusing log is not necessarily a bug in what actually ran.** If
  a run's log ever shows error lines appearing *before* the
  `apps_gone_free_emailer.py version: ...` line that's supposed to print
  first, that's Python's stdout/stderr buffering, not execution running
  out of order: `stdout` gets block-buffered when it isn't a real
  terminal (which it isn't in CI) and only flushes in chunks, while
  `stderr` always flushes immediately - so error/diagnostic lines
  (mostly `stderr`) can appear to happen "first" in a combined log even
  though the actual run order was correct. `PYTHONUNBUFFERED: "1"` is
  set on the Python-invoking workflow steps specifically so log order
  matches real execution order going forward.

### Troubleshooting: iGeeksBlog specifically parses to 0 apps

[#troubleshooting-igeeksblog-specifically-parses-to-0-apps](#troubleshooting-igeeksblog-specifically-parses-to-0-apps)

This happened three times during testing, and the incidents pointed at
different things - worth the full history rather than just "it's fixed
now," since the pattern across them is exactly why the debug-artifact
step below exists.

**First incident:** fetching `igeeksblog.com` directly (outside the
workflow) showed what looked like the page's content and structure
completely intact, so the leading theory was that the *request* wasn't
getting the same response the workflow needed - stale/minimal headers
reading as a bot, or GitHub Actions' well-known datacenter IPs getting
filtered. Headers got hardened (current Chrome version, `Accept-Language`,
`Accept-Encoding`, `Referer`) and the parser got more defensive
(`_find_heading()` checking non-semantic tags too, price matching no
longer requiring a childless tag) - reasonable fixes, but this theory
was never actually confirmed against the raw bytes the runner received,
just inferred from a separate fetch that turned out not to be equivalent.

**Second incident, with the actual raw HTML in hand:** the real page
came through completely fine (HTTP 200, ~108KB, "Today's Apps Gone
Free" heading present and intact) - so the first incident's bot-blocking
theory was likely wrong from the start. The actual bug: iGeeksBlog
renders each app's price as **two separate `<span>` elements** -
`<span class="label">Price: </span>` and `<span class="value">Free<sup>+</sup></span>`
with the "+" in a nested `<sup>` - so no single tag's text ever reads
"Price: Free". The original parser was built by inference from a
text/markdown rendering of the page (which flattens exactly this kind
of structural detail away), not from the real HTML, and simply never
had a chance of matching. `parse_igeeksblog()` now targets iGeeksBlog's
underlying listing plugin directly (`div.wpappbox`, with `.apptitle`,
`.appicon`, and `.price .value` inside it - visible as "WP-Appbox" in
an HTML comment around each entry) instead of inferring structure,
verified directly against a real saved copy of the page.

**The debug artifact exists precisely because of this gap.** Whenever a
source parses to 0 apps, the exact raw HTML that request received gets
saved and uploaded as a workflow artifact named **debug-html** (bottom
of that run's summary page, kept 14 days) - if it happens again,
download that file (or view-source the live page directly and copy the
relevant section) rather than reasoning from how the page reads when
converted to text, which is what went wrong the first time.

**Third incident, same symptom, one more layer down.** The `div.wpappbox`
rewrite above was itself tested against a real saved copy of the page -
and still shipped with a bug, because that saved copy had been trimmed
down to "the relevant part" (the app listings) and happened to leave out
the page's own `<h1>` title and its Table of Contents block. The page's
`<h1>` reads "Today's Apps Gone Free **on The App Store**" - which,
being a page about apps gone free, itself contains "gone free." Heading
search was checking h1 together with h2-h6, and since matches come back
in document order rather than grouped by level, that h1 - sitting near
the very top of the page - won over the real `<h2>` section heading
every time. The search then started walking from the wrong point,
immediately hit the Table of Contents' own unrelated `<h2>Table of
Contents</h2>`, and stopped right there. Fix: h2-h6 are checked first
(reliably body section headings on essentially any blog), h1 only as an
absolute last resort. The trimmed fixture is retired; the current test
suite runs against the complete page structure specifically so a
same-shaped bug can't hide in whatever got left out of an "obviously
irrelevant" trim next time either.

## Previewing the email design

[#previewing-the-email-design](#previewing-the-email-design)

```
python apps_gone_free_emailer.py preview
```

Writes `preview.html` / `preview.txt` from sample data through the real
`build_html()` / `build_plain_text()` functions - no network calls, no
state touched, nothing sent. Open `preview.html` in a browser any time
you want to check what the design actually looks like, including after
editing the colors/layout in `build_html()` - since it goes through the
real template code rather than a hand-copied mockup, it can't drift out
of sync with what an actual email looks like.

## Running locally instead

[#running-locally-instead](#running-locally-instead)

```
pip install -r requirements.txt
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export APPS_RECIPIENT="you@gmail.com"
python apps_gone_free_emailer.py generate
python apps_gone_free_emailer.py send
```

Schedule it yourself with cron (`crontab -e`):

```
0 1 * * * cd /path/to/apps-gone-free-emailer && /usr/bin/python3 apps_gone_free_emailer.py generate && /usr/bin/python3 apps_gone_free_emailer.py send >> apps_gone_free.log 2>&1
```
