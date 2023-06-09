import datetime
import os
import re
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from helpers import apology, login_required, lookup, usd
from werkzeug.security import check_password_hash, generate_password_hash

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure SQLite database connection
db = sqlite3.connect("finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Extract total shares for each stock from database
    try:
        portfolio = db.execute("""SELECT symbol, SUM(share) AS shares
                                  FROM shares
                                  WHERE user_id = ?
                                  GROUP BY symbol
                                  ORDER BY share DESC""",
                               session["user_id"])
    except sqlite3.Error:
        portfolio = []

    current_stocks = []

    # Populate the current_stocks list with user stocks + latest prices
    for stock in portfolio:
        # For each company stock, lookup() creates a dict
        # with keys: "name", "price", "symbol"
        current_stocks.append(lookup(stock["symbol"]))

        current_stocks[stock]["shares"] = stock["shares"]

    # Fetch current user cash
    user_cash = db.execute("SELECT username, cash FROM users WHERE id = ?",
                           session["user_id"])
    cash = user_cash[0]["cash"]

    # Calculate sum of user account cash and all shares worth
    shares_worth = 0
    for stock_new in current_stocks:
        shares_worth += (float(current_stocks[stock_new]["price"])
                         * int(current_stocks[stock_new]["shares"]))

    user_total = cash + shares_worth

    return render_template("index.html",
                           current_stocks=current_stocks,
                           cash=cash,
                           user_total=user_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Require user input - stock symbol
        buy_symbol = request.form.get("symbol")
        buy_stock = lookup(buy_symbol)

        if not buy_symbol:
            return apology("Must provide a stock symbol")
        if buy_stock is None:
            return apology("Symbol provided is not a valid stock")

        # Require user input - number of shares
        nr_of_shares = request.form.get("shares")

        if not nr_of_shares.isnumeric():
            return apology("Must provide a non-partial, positive number")
        if not nr_of_shares.isdigit():
            return apology("Must provide a non-partial, positive number")
        if int(nr_of_shares) < 1:
            return apology("Must provide a positive number")

        # Fetch user info from database
        user = db.execute("SELECT * FROM users WHERE id = ?",
                          session["user_id"])
        user_cash = user[0]["cash"]

        # Calculate amount of funds needed
        stock_price = buy_stock["price"]
        shares_to_buy_total = int(nr_of_shares) * stock_price

        # Render an apology, without completing a purchase,
        # if the user cannot afford the number of shares at the current price
        if shares_to_buy_total > user_cash:
            return apology("You do not have funds for this purchase")

        # Substract cash spent from user account
        user_cash_new = user_cash - shares_to_buy_total
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   user_cash_new, session["user_id"])

        # Update shares table with new purchase
        timestamp = datetime.datetime.now()
        db.execute("""INSERT INTO shares (user_id, symbol, share, price, time)
                      VALUES (?, ?, ?, ?, ?)""",
                   session["user_id"], buy_symbol, nr_of_shares,
                   stock_price, timestamp)

        # UI feedback
        flash(
            f"Purchased {nr_of_shares} {buy_stock['name']} stock for ${shares_to_buy_total}")

        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query databse for list of user transactions
    history_from_db = db.execute("""SELECT symbol, share, price, time
                                    FROM shares WHERE user_id = ?
                                    ORDER BY time DESC""",
                                 session["user_id"])

    return render_template("history.html", history=history_from_db)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    session.clear()

    if request.method == "POST":

        if not request.form.get("username"):
            return apology("Must provide username", 403)
        if not request.form.get("password"):
            return apology("Must provide password", 403)

        user = db.execute("""SELECT * FROM users WHERE username = ?""",
                          request.form.get("username"))

        if (len(user) != 1
                or not check_password_hash(user[0]["hash"], request.form.get("password"))):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = user[0]["id"]

        return redirect("/")

    # User reached route via GET
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        # Require user input - stock symbol
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("Must provide stock symbol")

        # Require that the symbol provided is valid
        quote_response = lookup(symbol)

        if quote_response is None:
            return apology("Must provide a valid stock symbol")

        return render_template("quoted.html",
                               name=quote_response["name"],
                               symbol=quote_response["symbol"],
                               price=quote_response["price"])

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        # Require username
        username = request.form.get("username")

        # Require password
        password = request.form.get("password")

        # Require password confirmation
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Must provide a username")

        if not password:
            return apology("Must provide a password")

        if not confirmation:
            return apology("Must provide a matching password in both boxes")

        # Validate password for minimum number of character types used
        re_pattern = "^(?=.*?[a-z])(?=.*?[A-Z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-]).{8,}$"
        validation = re.match(re_pattern, password)
        if validation is None:
            return apology("""Provide a password with a min number of 8
                              characters and one special, one numeric, one
                              uppercase and one lowercase letter characters""")

        if password != confirmation:
            return apology("Passwords do not match")

        # Hash the users password with generate_password_hash
        password_hash = generate_password_hash(password)

        # Add new user, storing a hash, not the password itself
        try:
            user_id = db.execute("""INSERT INTO users (username, hash)
                                   VALUES(?, ?)""",
                                 username, password_hash)
        except sqlite3.Error:
            return apology("That username is already taken")

        # Log user in
        session["user_id"] = user_id

        # UI feedback
        flash("Registered!")

        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Require user input - stock symbol
        sell_symbol = request.form.get("symbol")
        sell_stock = lookup(sell_symbol)
        sell_user_shares = int(request.form.get("shares"))

        if not sell_symbol or sell_symbol == "Symbol":
            return apology("Must choose a stock owned")
        if sell_stock is None:
            return apology("Must choose a valid stock owned")

        # Fetch user info of shares of the stock provided
        user_shares = db.execute("""SELECT SUM(share) AS shares
                                   FROM shares
                                   WHERE user_id = ? AND symbol = ?
                                   GROUP BY symbol""",
                                 session["user_id"], sell_symbol)

        user_shares_nr = int(user_shares[0]["shares"])

        if user_shares_nr < 1:
            return apology("You do not own any shares of that stock")
        if sell_user_shares < 0:
            return apology("Must provide a positive number")
        if sell_user_shares > user_shares_nr:
            return apology("""Must provide a number less than or equal
                              to the shares that you own""")

        # Fetch latest stock price
        currentstock_price = sell_stock["price"]

        # Fetch current user account cash balance
        user = db.execute("SELECT * FROM users WHERE id = ?",
                          session["user_id"])
        user_cash = user[0]["cash"]

        # Calculate amount of cash for sold shares
        profit = currentstock_price * sell_user_shares
        user_cash_new = user_cash + profit
        sold_user_shares = sell_user_shares - 2 * sell_user_shares

        # Substract shares from portfolio
        # (add entry with negative shares amount to shares table)
        time = datetime.datetime.now()
        db.execute("""INSERT INTO shares (user_id, symbol, share, price, time)
                      VALUES (?, ?, ?, ?, ?)""",
                   session["user_id"], sell_symbol, sold_user_shares,
                   currentstock_price, time)

        # Add cash from sale to user account
        db.execute("UPDATE users SET cash = ? WHERE id = ?",
                   round(user_cash_new, 2), session["user_id"])

        # UI feedback
        flash("Stock sold!")

        return redirect("/")

    # Retrieve a list of user shares of stocks
    user_stocks = db.execute("""SELECT symbol FROM shares
                                WHERE user_id = ?
                                GROUP BY symbol HAVING SUM(share) > 0""",
                             session["user_id"])

    return render_template("sell.html", user_stocks=user_stocks)
