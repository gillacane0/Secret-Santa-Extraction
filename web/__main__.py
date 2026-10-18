"""Run the website on your computer: uv run python -m web"""

from . import create_app

# Locally the site runs on plain http, so the login cookie can't require https.
create_app({"SESSION_COOKIE_SECURE": False}).run(debug=True)
