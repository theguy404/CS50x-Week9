import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    
    # list the stocks for this user
    stocks = db.execute("SELECT * FROM transactions WHERE user_id = :id AND owned > :owned",
                        id=session.get("user_id"),
                        owned=0)
    user = db.execute("SELECT cash FROM users WHERE id = :id",
                      id=session.get("user_id"))
    value = user[0]['cash']
    for i in range(len(stocks)):
        total = stocks[i]['price'] * stocks[i]['shares']
        value = value + total
    return render_template("index.html", stocks=stocks, cash=round(user[0]['cash'], 2), value=value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Get Cash from database for this user
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
                          id=session.get("user_id"))
        cash = cash[0]['cash']
        
        # Get the stock price from the api
        stockPrice = lookup(request.form.get("symbol"))
        
        if not stockPrice:
            return apology("Stock not found", 400)
        stockName = stockPrice['name']
        stockPrice = float(stockPrice['price'])
        
        test = request.form.get("shares").isdecimal()
        
        if not test:
            return apology("Not valid share", 400)
        
        # Ensure user has the money for the purchase
        if stockPrice * float(request.form.get("shares")) > float(cash):
            return apology("Not enough cash for this transaction", 400)
        else:
            # Adds shares to users account
            db.execute("INSERT INTO transactions(type,owned,user_id,symbol,name,price,shares) VALUES(:type, :owned, :id, :symbol, :name, :price, :shares)",
                       type="buy",
                       owned=request.form.get("shares"),
                       id=session.get("user_id"),
                       symbol=request.form.get("symbol"),
                       name=stockName,
                       price=stockPrice,
                       shares=request.form.get("shares"))
            
            # Removes funds from users cash
            cost = stockPrice * float(request.form.get("shares"))
            db.execute("UPDATE users SET cash = :remaining WHERE id = :id",
                       remaining=cash - cost,
                       id=session.get("user_id"))
                        
            # return user to index
            flash("Bought!")
            return index()
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    return jsonify("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :id",
                              id=session.get("user_id"))
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
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
        stockQuote = lookup(request.form.get("symbol"))
        if not stockQuote:
            return apology("Stock not found", 400)
        else:
            return render_template("quoted.html", stockQuote=stockQuote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("No Username", 400)
        if not request.form.get("password"):
            return apology("Missing Password", 400)
        if not request.form.get("confirmation"):
            return apology("Must confirm the password", 400)
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)
        
        test = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if test:
            return apology("Username Taken", 400)
        
        db.execute("INSERT INTO users(username,hash) VALUES(:username, :hash)",
                   username=request.form.get("username"),
                   hash=generate_password_hash(request.form.get("password"), ))
        session.get("user_id")
        return redirect("/")
        
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    
    if request.method == "POST":
        # check if user has enough stocks to sell of selected symbol
        stocks = db.execute("SELECT * FROM transactions WHERE user_id = :id AND owned > :owned AND symbol = :symbol",
                            id=session.get("user_id"),
                            owned=0,
                            symbol=request.form.get("symbol"))
        count = 0
        toSell = int(request.form.get("shares"))
        for i in range(len(stocks)):
            count = count + int(stocks[i]['shares'])
            
        if count < toSell:
            return apology("Not enough shares availible for this transaction.")
        else:
            # Get stock price
            stockPrice = lookup(request.form.get("symbol"))
            
            # loop through transactions from oldest to newest and remove ownership
            for i in range(len(stocks)):
                if toSell > stocks[i]['owned']:
                    toSell = toSell - stocks['owned']
                    db.execute("UPDATE transactions SET owned = :owned WHERE transaction_id = :id",
                               owned=0,
                               id=stocks[i]['transaction_id'])
                        
                else:
                    db.execute("UPDATE transactions SET owned = :owned WHERE transaction_id = :id",
                               owned=stocks[i]['owned'] - toSell,
                               id=stocks[i]['transaction_id'])
                    toSell = 0
                        
            # add money of shares to sell times current stock price to cash
            addmoney = stockPrice['price'] * float(request.form.get("shares"))
            user = db.execute("SELECT * FROM users WHERE id = :id",
                              id=session.get("user_id"))
            db.execute("UPDATE users SET cash = :newcash WHERE id = :id",
                       newcash=float(user[0]['cash']) + addmoney,
                       id=session.get("user_id"))
                        
            # add sold transaction to history
            db.execute("INSERT INTO transactions(type,owned,user_id,symbol,name,price,shares) VALUES(:type, :owned, :id, :symbol, :name, :price, :shares)",
                       type="sell",
                       owned=0,
                       id=session.get("user_id"),
                       symbol=request.form.get("symbol"),
                       name=stockPrice['name'],
                       price=stockPrice['price'],
                       shares=request.form.get("shares"))
                
            # display index with updates and sold message
            flash("SOLD!")
            return index()
    else:
        stocks = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = :id AND owned > :owned",
                            id=session.get("user_id"),
                            owned=0)
        return render_template("sell.html", stocks=stocks)


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    if request.method == "POST":
        data = db.execute("SELECT * FROM users WHERE id = ?", session.get("user_id"))
        
        if not check_password_hash(data[0]["hash"], request.form.get('old')):
            return apology("Old Password Incorrect", 400)
        if request.form.get("npassword") != request.form.get("cpassword"):
            return apology("New passwords do not match", 400)
        
        nhash = generate_password_hash(request.form.get("npassword"), )
        if nhash:
            db.execute("UPDATE users SET hash = ? WHERE id = ?", nhash, session.get("user_id"))
            return index()
    else:
        return render_template("password.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
