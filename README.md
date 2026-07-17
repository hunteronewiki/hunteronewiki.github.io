# Kingshot Wiki

A community wiki for **Kingshot**, generated from a folder of Markdown notes.
104 pages — events, all 34 heroes across 7 generations, gear guides, alliance
announcements, and the `[ONE]OneForAll` playbook — with working search,
hero/event infoboxes, and "what links here" backlinks, deployed free on
GitHub Pages.

**Live structure:** you edit plain `.md` files in `content/`, run one command,
and a full static website appears in `docs/`. GitHub Pages serves `docs/`
directly — no server, no database, no ongoing hosting cost.

---

## 1. One-time setup

You need **Python 3.9+** and **VS Code** (or any editor).

1. Open this folder in VS Code (`File → Open Folder…`).
2. Open the built-in terminal (`` Ctrl+` ``  /  `` Cmd+` ``).
3. Install the one dependency this project uses:

   ```bash
   pip install -r requirements.txt
   ```

   (On some systems you may need `pip3` instead of `pip`, or
   `pip install -r requirements.txt --break-system-packages`.)

That's it — no Node, no Ruby, no Jekyll.

---

## 2. Editing content

All the actual wiki text lives in **`content/`**, organized exactly like the
original vault:

```
content/
  00 Home/                 → the homepage's intro text
  01 Events/                → one .md file per event
  02 Heroes/                 → overview & generation-summary pages
    Individual Heroes/       → one .md file per hero
  03 Gear/
  04 Announcements/
  05 Reference/
  06 OneForAll Playbook/
  07 Game Systems/
```

Each file supports:

- **Frontmatter** — `tags: [...]` and `aliases: [...]` at the top
- **Wikilinks** — `[[Bear Hunt]]` or `[[Hero Gear Guide|Hero Gear]]`, exactly
  like Obsidian. The link target must match another file's name exactly.
- **Callouts** — `> [!tip] Title`, `> [!warning] Title`, `> [!info] Title`,
  `> [!important] Title`, followed by `>`-prefixed body lines
- **Infoboxes** — automatic. Any `**Key:** value` lines directly under the
  `# Title` become the sidebar fact box (this is how every hero/event page
  gets its info card — no extra markup needed)
- **"See also: [[A]], [[B]]"** as the last line — automatically becomes a
  styled "See also" box
- Tables, checklists (`- [ ]`), code blocks, everything else in standard
  Markdown

**To add a new page:** drop a new `.md` file in the right folder, following
the pattern of its neighbors, and link to it from at least one other page
(or from `content/00 Home/Home.md`, which controls the sidebar ordering).

**To rename or delete a page:** just rename/delete the file. Run the build —
if you left a dangling `[[wikilink]]` to something that no longer exists,
the build will still succeed, but that link will silently render as plain
text instead of a link. (Nothing crashes; nothing to debug under time
pressure before an event goes live.)

---

## 3. Building the site

Every time you change something in `content/`, regenerate the website:

```bash
python3 build.py
```

This rewrites everything in **`docs/`** from scratch (deletes and rebuilds
it), including `search-index.json` and copies of `static/css` and
`static/js`. It takes well under a second for the whole vault.

**Preview it locally before pushing**, so you're never guessing:

```bash
cd docs
python3 -m http.server 8000
```

Then open `http://localhost:8000` in a browser.

---

## 4. Putting it on GitHub Pages

If you haven't already:

1. Create a new repository on GitHub (e.g. `kingshot-wiki`) — public,
   no README/license/.gitignore (you already have those here).
2. In this project's terminal:

   ```bash
   git init
   git add .
   git commit -m "Initial Kingshot wiki"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
   git push -u origin main
   ```

3. On GitHub, go to **Settings → Pages**.
4. Under **Build and deployment → Source**, choose **Deploy from a branch**.
5. Branch: **`main`**, folder: **`/docs`**. Save.
6. GitHub gives you a URL like `https://YOUR-USERNAME.github.io/YOUR-REPO/`
   — it's live within a minute or two.

**From then on, your whole workflow is:**

```bash
python3 build.py
git add .
git commit -m "Update Bear Hunt notes"
git push
```

The live site updates automatically within a minute of pushing — no
GitHub Actions, no build servers, nothing that can silently fail. Every
internal link and asset path is generated *relative* to the page, so this
works correctly whether your Pages URL is a subpath
(`username.github.io/repo-name/`), a root domain, or a custom domain later —
you don't need to configure a "base URL" anywhere.

---

## 5. How it's built (if you want to tweak it)

- **`build.py`** — the whole generator. It's one file, organized top to
  bottom: text/markdown helpers → wikilink & callout parsing → HTML
  templates → the main build loop. Read it like a short book if you want
  to change how something renders.
- **`static/css/style.css`** — every visual choice: colors, type, layout,
  the infobox/callout/dossier-card styling. Site-wide colors are CSS custom
  properties at the very top of the file (`--brass`, `--banner`, `--steel`,
  etc.) if you want to reskin it.
- **`static/js/main.js`** — search (header + `/search/` page), the mobile
  sidebar drawer, the random-page button, and copy-to-clipboard on
  announcement code blocks. No frameworks, no build step.
- **Ordering** — the sidebar and category pages inherit their reading order
  from `content/00 Home/Home.md`'s own outline, so reordering sections
  there reorders the whole site.
- **Search** is a static `docs/search-index.json` (title/url/category/tags
  for every page) fetched once by the browser and filtered client-side —
  no server, works offline once a page has loaded.

### Small customizations

- Site name / tagline: `SITE_NAME` and `SITE_TAGLINE` near the top of
  `build.py`.
- Category names/descriptions/icons: `CATEGORY_LABELS`,
  `CATEGORY_DESCRIPTIONS`, `CATEGORY_ICONS` in `build.py`.
- Colors/fonts: the `:root` block at the top of `style.css`.

### Ideas for later (not built yet, easy to ask for)

- A GitHub Actions workflow that runs `build.py` automatically on every
  push, so you never have to remember to run it locally.
- A light-mode toggle alongside the dark theme.
- Hero portrait images once you have your own screenshots to use (no game
  art is included here, since it isn't ours to redistribute).

---

## Credits & disclaimer

Fan-made reference material for Kingshot, built from `[ONE]OneForAll`'s
internal alliance notes. Not affiliated with or endorsed by Kingshot's
developer or publisher. Game numbers and mechanics reflect current best
understanding at time of writing and will drift after patches — update the
source `.md` files as your alliance discovers changes.
