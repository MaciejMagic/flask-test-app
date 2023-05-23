import os
import urllib.parse
from functools import wraps
from typing import Any, Union

import requests
from flask import redirect, render_template, session


def apology(message: str, code: int = 400) -> Union[render_template, int]:
    """Render message as an apology to user."""

    def escape(special):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            special = special.replace(old, new)
        return special
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(function):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """

    @wraps(function)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return function(*args, **kwargs)
    return decorated_function


def lookup(symbol: str) -> (dict[str, Any] | None):
    """Look up quote for symbol."""

    try:
        api_key = os.environ.get("API_KEY")
        url = f"https://cloud.iexapis.com/stable/stock/{urllib.parse.quote_plus(symbol)}/quote?token={api_key}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        quote = response.json()
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None


def usd(value) -> str:
    """Format value as USD."""

    return f"${value:,.2f}"
