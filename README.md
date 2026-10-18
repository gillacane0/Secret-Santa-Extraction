# Secret Santa Extraction

A small desktop app to organize a Secret Santa with friends: it draws who gives a gift to whom and emails everyone their match, so not even the organizer knows the result.

- **Exclusions**: for each person, the people they must never get (a partner, a sibling…).
- **History**: the app remembers past draws and avoids repeating the pairings of the last few years, without you typing them in.
- **Single chain** (optional): everyone is in one loop, A → B → C → … → A, nice for the gift exchange.
- **Saved groups**: next year you open the file and just change who's in or out.
- **Test run**: checks everything and sends a sample email only to you.

## Setup

You need [uv](https://docs.astral.sh/uv/) (or Python 3.14 with `pip install python-dotenv`).

```
uv sync
```

### Email

The app sends the emails from your account. Copy `.env.example` to `.env` and fill it in:

```
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

`.env` is ignored by git, so your password stays on your computer.

For Gmail, `SMTP_PASSWORD` is **not** your normal password but an *app password*: a 16-letter code Google generates for apps like this one. Two-step verification must be on; then go to your Google account, search for **"App passwords"** and create one. Other providers work too: set `SMTP_HOST` and `SMTP_PORT` in `.env`.

## Usage

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

## About the history

Past pairings are saved as salted hashes, so opening the group file doesn't spoil who had whom. This protects against accidental spoilers, not against someone determined: with so few possible pairs, anyone with the code could try them all.

## Tests

```
uv run pytest
```
