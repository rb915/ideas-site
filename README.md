# Notion Ideas — Auto-Updating Static Site

This repo fetches ideas from your Notion database and publishes them to a mobile-friendly static HTML page. It rebuilds automatically every hour.

## One-Time Setup

### 1. Create a Notion integration (2 min)

1. Go to https://www.notion.so/profile/integrations
2. Click **"+ New integration"**
3. Name it something like `Ideas Site`
4. Associated workspace: pick yours
5. Type: **Internal**
6. Click **Save**, then copy the **"Internal Integration Secret"** — this is your `NOTION_TOKEN` (starts with `ntn_` or `secret_`)

### 2. Give the integration access to your database (1 min)

1. Open your Notion ideas database in a browser
2. Click the `•••` menu in the top right
3. **Connections → Connect to → Ideas Site**
4. Approve it

### 3. Get your database ID (30 sec)

Look at the URL of your database. It looks like:
```
https://www.notion.so/yourworkspace/348043efd9cb8015be1be5c33a3879d7?v=...
```
The 32-character string (`348043ef...3879d7`) is your `NOTION_DATABASE_ID`.

### 4. Push this code to a new GitHub repo (5 min)

```bash
# In this directory
git init
git add .
git commit -m "Initial commit"
# Create a new repo on github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

### 5. Add your secrets to GitHub (1 min)

In your new repo on GitHub:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **"New repository secret"** — add:
   - Name: `NOTION_TOKEN`, Value: the token from step 1
3. Click **"New repository secret"** again — add:
   - Name: `NOTION_DATABASE_ID`, Value: the ID from step 3

### 6. Enable GitHub Pages (1 min)

1. Go to **Settings → Pages**
2. Under **Build and deployment → Source**, pick **"GitHub Actions"**

### 7. Trigger the first build

Go to the **Actions** tab, click **"Build and deploy ideas page"**, then **"Run workflow"**. After ~1 minute it'll finish and your site will be live at:

```
https://YOUR_USERNAME.github.io/YOUR_REPO/
```

Bookmark it on your phone. Done.

---

## How it updates

- **Automatically**: every hour, on the hour (via GitHub Actions schedule)
- **On push**: any time you commit to `main`
- **On demand**: Actions tab → "Run workflow"

If you want it faster than hourly, edit `.github/workflows/build.yml` and change the cron line. The minimum GitHub allows is every 5 minutes: `*/5 * * * *`.

## Database schema expected

The script looks for these property names (case-sensitive):

- **Title** (the built-in Notion title property — can be named anything, the script finds it by type)
- `Slot` — optional text/select (e.g. "12PM")
- `Source` — optional text/select (e.g. "RyMaxHermes")
- `Created` — optional date

It also pulls the **body** of each page (everything below the properties) and uses that as the idea's content. If you also have a `Content` rich-text property, it falls back to that when the body is empty.

## Customizing

- **Themes/grouping**: edit the `categorize()` function and `SECTIONS` list in `build.py`
- **Styling**: edit the CSS in `PAGE_TEMPLATE` at the top of `build.py`
- **Update frequency**: edit the cron line in `.github/workflows/build.yml`

## Running locally

```bash
export NOTION_TOKEN=ntn_xxxxxxxxxxxx
export NOTION_DATABASE_ID=348043efd9cb8015be1be5c33a3879d7
python3 build.py
# Opens in public/index.html
```
