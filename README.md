# Secret Santa Extraction

Organize a Secret Santa with your friends. The draw respects who must never get whom, avoids repeating the pairings of the last few years, and the organizer never sees who got whom.

There are two ways to use it:

- **The website**: friends join with a link (for example shared in a WhatsApp group), and each person sees online who they got, together with that person's wishlist.
- **The desktop app**: you enter everybody yourself, and each person gets their match by email.

Both use the same draw and the same history, and the website's backups open in the desktop app too.

## The website

- Friends join with the invite link, choosing a PIN, and can write a wishlist.
- The organizer page manages participants, exclusions and settings, and never shows the matches.
- After the draw, each person logs in with their PIN and sees only who they got.
- Next year you start a new round, and the pairings of the last years are avoided automatically.
- Wrong PINs lock the login for longer and longer, so nobody can guess someone else's.

### Try it on your computer

You need [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run python -m web
```

Then open http://127.0.0.1:5000.

### Put it online for free (PythonAnywhere)

1. Create a free account on [PythonAnywhere](https://www.pythonanywhere.com). The site will be at `https://<username>.pythonanywhere.com`.
2. Open a **Bash console** and run:

   ```
   git clone https://github.com/gillacane0/Secret-Santa-Extraction.git
   cd Secret-Santa-Extraction
   mkvirtualenv --python=/usr/bin/python3.13 santa
   pip install -r requirements.txt
   python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
   ```

   The last command creates the secret key that keeps people logged in.
3. In the **Web** tab, click **Add a new web app**, then choose **Manual configuration** and **Python 3.13**. On the page of the new web app:
   - **Virtualenv**: enter `/home/<username>/.virtualenvs/santa`.
   - **Static files**: add the URL `/static/` with the directory `/home/<username>/Secret-Santa-Extraction/web/static`.
   - **WSGI configuration file**: open it, delete everything and write:

     ```python
     import sys
     sys.path.insert(0, "/home/<username>/Secret-Santa-Extraction")
     from wsgi import application
     ```

   - Turn on **Force HTTPS**, then click **Reload**.

Free sites are switched off after a month: while the Secret Santa is going on, open the **Web** tab once a month and click the button that keeps the site running. Free accounts that stay unused for a long time can be deleted, so download a backup from the organizer page now and then. You can restore it from the home page.

To update the site after a `git push`, run `git pull` in the project folder from a Bash console, then click **Reload** in the **Web** tab. If the dependencies changed, run `workon santa` and `pip install -r requirements.txt` before reloading.

## The desktop app

- **Exclusions**: for each person, the people they must never get (a partner, a sibling…).
- **History**: the app remembers past draws and avoids repeating the pairings of the last few years.
- **Single chain** (optional): everyone is in one loop, A → B → C → … → A, nice for the gift exchange.
- **Saved groups**: next year you open the file and just change who's in or out.
- **Test run**: checks everything and sends a sample email only to you.

### Email setup

The app sends the emails from your account. Copy `.env.example` to `.env` and fill it in:

```
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

`.env` is ignored by git, so your password stays on your computer.

For Gmail, `SMTP_PASSWORD` is **not** your normal password but an *app password*: a 16-letter code Google generates for apps like this one. Two-step verification must be on; then go to your Google account, search for **"App passwords"** and create one. Other providers work too: set `SMTP_HOST` and `SMTP_PORT` in `.env`.

### Usage

```
uv run extraction.py
```

1. Add the participants: name, email and, optionally, who they must never get (comma-separated).
2. Set the budget and how many years of past pairings to avoid.
3. **Save** the group (it goes in `groups/`, which is ignored by git since it holds your friends' emails).
4. **Test run** to check that everything works: you'll receive a sample email.
5. **Draw and send emails**. The draw is recorded in the group file for the next years.

If the draw can't be done, the app tells you why (for example "Anna has nobody left to give a gift to") instead of getting stuck. If some emails fail, you can retry just those.

`group.example.json` shows the format of a group file.

## How secret is it?

The pages and the emails never show the organizer who got whom, but someone determined could still find out:

- Past pairings are saved as salted hashes, so opening a group file or a backup doesn't spoil who had whom. With so few possible pairs, though, anyone with the code could try them all.
- The website keeps this year's matches in its database, so whoever manages the hosting account could read them from there.
- The desktop app sends the emails from your account, so a copy stays in your **Sent** folder. Use an account you don't open, or don't peek!

## Tests

```
uv run pytest
```
