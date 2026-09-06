# PTI Stations Performance Analysis

A small web app for Massar United Co. that you open in a browser -- from your
laptop or your phone, it's the same app and the same data. You upload each
period's statistics sheet, it stores the numbers, compares them against every
previous period, and can generate an executive PDF report (Arabic or English,
Cairo font, your logo) on demand.

This document is a step-by-step guide to putting it online for free, written
for someone doing this for the first time. It takes about 15-20 minutes and
you won't need to write any code.

## How it works, in one paragraph

The app's code runs on a free hosting service called **Streamlit Community
Cloud**. Its data (every period you've ever uploaded) lives in a free
database on a service called **Supabase**. Because both are on the internet
rather than on your laptop, opening the same web address from your phone
shows the exact same data. You only set this up once; after that, using the
app is just "open the link, upload a sheet, or generate a report."

---

## One-time setup

### Step 1 -- Put the code on GitHub

GitHub is where the app's code lives so Streamlit can find it. You don't
need to know git.

1. Go to **github.com** and create a free account if you don't have one.
2. Click the **+** icon (top right) → **New repository**.
3. Name it `pti-spa-app` (any name works), leave it **Public** or **Private**
   (either is fine for Streamlit Community Cloud), and click **Create repository**.
4. On the new repository's page, click **uploading an existing file**.
5. Drag in *every file and folder* from the `pti-spa-app` folder you were
   given (keep the folder structure -- `pages/`, `assets/`, `templates/` and
   all, plus `requirements.txt`, `packages.txt`, `.streamlit/config.toml`, and
   `app.py`).
6. Scroll down and click **Commit changes**.

### Step 2 -- Create a free database (Supabase)

1. Go to **supabase.com** → **Start your project** → sign up for free.
2. Click **New project**. Pick any name (e.g. `pti-spa`), set a database
   password (write it down somewhere safe), choose a region close to Saudi
   Arabia (e.g. an EU or Middle East region if offered), and click **Create
   new project**. Wait a minute or two while it provisions.
3. Once it's ready, go to **Project Settings** (gear icon) → **Database**.
4. Find **Connection string** and choose the **URI** tab. It looks like:
   `postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxx.supabase.co:5432/postgres`
5. Copy that, and replace `[YOUR-PASSWORD]` with the database password you
   set in step 2. Keep this handy for the next step.

> Free Supabase projects pause themselves after about a week with no
> activity. Opening the app and using it resumes the database automatically
> (it just takes a few extra seconds on the first request); if it's been
> paused a long time, Supabase's dashboard has a "Restore/Resume" button.

### Step 3 -- Deploy the app (Streamlit Community Cloud)

1. Go to **share.streamlit.io** → sign in with your GitHub account.
2. Click **Create app** (or **New app**) → **From existing repo**.
3. Pick the `pti-spa-app` repository you created in Step 1, branch `main`,
   and set the main file path to `app.py`.
4. Before clicking Deploy, open **Advanced settings** → **Secrets**, and
   paste this in (with your real connection string from Step 2):

   ```toml
   DATABASE_URL = "postgresql://postgres:your-password@db.xxxxxxxx.supabase.co:5432/postgres"
   ```

5. Click **Deploy**. The first build takes a few minutes (it's installing
   the PDF-generation library and its system packages listed in
   `packages.txt`). When it's done, you'll have a URL like
   `https://your-app-name.streamlit.app`.

That URL is the app -- open it on your laptop, open it on your phone, and
they both show the same data because they're both talking to the same
Supabase database.

**Tip:** on your phone, open the URL in the browser and use "Add to Home
Screen" so it behaves like an app icon.

---

## Using the app

- **📤 Upload** -- upload each period's Excel/CSV (or PDF as a fallback),
  check the preview, fill in the period dates (and complaints/Absher % if you
  track them), then save.
- **📊 Dashboard** -- pick a period and see KPIs, station comparisons, trend
  charts, and flagged weak points/opportunities.
- **📄 Reports** -- pick a period and a language (Arabic or English) and
  generate the executive PDF report with your logo and Cairo font.
- **⚙️ Settings** -- update the company name in each language, replace the
  logo, adjust the pass-rate/absence-rate thresholds used to flag stations,
  and rename/deactivate stations.

## Updating the app later

Edit a file directly on GitHub (open the file, click the pencil icon, edit,
commit) and Streamlit Community Cloud redeploys automatically within a
minute or two. No separate "upload" step needed.

## The statistics sheet format

The Upload page has a "Expected columns" section with a downloadable Excel
template. In short, one row per station with these columns (Arabic headers
shown, English equivalents also recognized):

| المحطة (Station) | المواعيد (Appointments) | الحضور (Attendance) | الغياب (Absence) | لأول مرة (First-time) | إعادة الفحص 1 (Retest 1) | إعادة الفحص 2 (Retest 2) | ناجحة (Passed) | راسبة (Failed) |
|---|---|---|---|---|---|---|---|---|

If your only export option is the PDF "Operations Department Report" from
the inspection system, the Upload page also accepts that directly -- it's
just a little more fragile than Excel/CSV if that PDF's layout ever changes.

## Troubleshooting

- **"App error" right after deploying / build fails mentioning `weasyprint`
  or `cairo`:** double-check `packages.txt` made it into the GitHub upload
  (it must sit next to `requirements.txt`, not inside a subfolder).
- **Dashboard/Reports say "No data yet":** you haven't uploaded a period yet,
  or the app is pointing at a different database than you think -- check
  ⚙️ Settings → "Database connection info".
- **Data from your phone doesn't show up on your laptop (or vice versa):**
  that almost always means `DATABASE_URL` wasn't set in Streamlit's Secrets,
  so the app fell back to a local file that only exists on one device/deploy.
  Re-check Step 3.4 above.
- **Everything is free**, but Streamlit Community Cloud apps that get zero
  traffic for a long time go to sleep and take ~30 seconds to wake up on the
  next visit -- that's normal, not a bug.
