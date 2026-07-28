# iOS Apps Gone Free Emailer (runs on GitHub Actions, no local computer needed)

Emails you a digest of iOS apps that have gone free today, automatically,
via GitHub's free scheduled-workflow runners.

Modeled on [tech-price-mailer](https://github.com/tuongphantrue/tech-price-mailer) and
[currency-rate-emailer](https://github.com/tuongphantrue/currency-rate-emailer) -
same generate/send two-phase shape, same Gmail-SMTP delivery, same
dedup-via-state-branch trick.

## Important: read this before relying on it

[#important-read-this-before-relying-on-it](#important-read-this-before-relying-on-it)

A lot of the sites people remember for this have quietly died. Before
building this, I checked what's actually still alive in 2026:

| Site | Status |
| --- | --- |
| AppShopper.com | Shut down 2021-06-30. |
| iOSnoops.com | Was still posting in 2023; its own homepage now just says "we have decided to shut down the site." |
| AppAdvice.com "Apps Gone Free" | Stopped being updated in early 2026 (Apple tightened App Review enforcement on free-to-paid price-flip promos). The page is still online but frozen on a mid-January 2026 post. |
| AppRaven (appraven.net) | Still active, but it's a client-side JS app with no server-rendered HTML - nothing for a plain scraper to read. |
| AppsHunter.io, 148apps.com | Still active, but general app catalogs / gaming-news sites, not a clean "gone free today" list. |
| **iGeeksBlog.com** | **Still active and actually updated daily** - one bookmarkable page it edits in place, not per-day archive posts. |

So this scrapes iGeeksBlog's [Today's Apps Gone
Free](https://www.igeeksblog.com/paid-iphone-apps-gone-free/) page, the
same way tech-price-mailer scrapes MemoryZone.vn. Every app it finds is
then cross-checked against Apple's own iTunes Lookup API - a plain
"Free" listing (was a normal paid download, now $0) that no longer shows
$0.00 there gets dropped as stale rather than emailed. "Free+" listings
(the app was already free to download and a premium/subscription tier
got unlocked for now) can't be verified the same way, since a free
download always shows $0.00 whether or not the unlock promo is still
live - those go out on iGeeksBlog's own editorial word.

Because it's one hand-curated site, this will only ever catch what that
site picks - it's not an exhaustive scan of the whole App Store. See
"Adding another source" below if you find a second site worth adding.

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
- cron: "0 1 * * *"
```

Cron format is `minute hour day month weekday`, always in **UTC**.

- `0 1 * * *` -> once a day at 1am UTC (8am Vietnam, UTC+7) - current setting
- `0 1,13 * * *` -> twice a day, 1am and 1pm UTC
- `0 */6 * * *` -> every 6 hours

iGeeksBlog updates that page roughly daily, so running more than a couple
times a day mostly just means more "nothing new" runs, not more emails.

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
COUNTRY: "us"                        # App Store storefront for the iTunes Lookup cross-check
COOLDOWN_DAYS: "21"                  # don't re-email the same app within this many days
ALWAYS_SEND: "false"                 # "true" = still send a "nothing new" email every run
TIMEZONE: "Asia/Ho_Chi_Minh"         # only affects the timestamp shown in the email
STATE_FILE: "state/notified.json"    # dedup state file path
IGEEKSBLOG_URL: "https://www.igeeksblog.com/paid-iphone-apps-gone-free/"
ALLOW_INSECURE_SSL_FALLBACK: "false" # last-resort TLS bypass
```

## Adding another source

[#adding-another-source](#adding-another-source)

`SOURCES` near the top of `apps_gone_free_emailer.py` is a list of
`{"name", "url", "parser"}` - currently just the one entry for
iGeeksBlog. `fetch_all_sources()` already fetches every entry in that
list, tolerates any one of them failing, and dedupes apps by App Store
id across sources. To add a second site, write a
`parse_<site>(html) -> [{"id", "name", "icon", "url", "price_label"}, ...]`
function (see `parse_igeeksblog()` for the shape - it deliberately
doesn't depend on exact CSS class names, just link/heading structure, in
case that's a useful pattern to copy) and append it to `SOURCES`.

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
- GitHub Actions free tier includes 2,000 minutes/month for private repos.
- You can also trigger it manually anytime via the "Run workflow" button.
- If a run logs "0 apps scraped from every source" (check the Actions
  log), iGeeksBlog's page structure has probably changed - open the page,
  view source, and adjust `parse_igeeksblog()` in
  `apps_gone_free_emailer.py` to match. This is exactly the same kind of
  "site changed its markup" caveat tech-price-mailer has for
  MemoryZone.vn - unofficial scrapers can break without notice.
- Worth checking iGeeksBlog's current `robots.txt` / terms before
  running this unattended long-term: <https://www.igeeksblog.com/robots.txt>
- This tool isn't affiliated with iGeeksBlog or Apple; it just reads a
  public page and a public Apple API. Please don't crank the schedule up
  to something aggressive (e.g. every few minutes) against a small site's
  server for a page that only changes about once a day.
- This is a personal notification tool, not investment or purchase advice.

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
