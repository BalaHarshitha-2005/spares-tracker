from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table
from reportlab.lib import colors
import os

app = Flask(__name__)
app.secret_key = "sri_srinivasa_secret"

DATABASE = "database.db"

# -----------------------
# LOAD SPARES CSV
# -----------------------
df = pd.read_csv("spares.csv", encoding="latin1")
spares_list = df["Part Description"].dropna().unique().tolist()


# -----------------------
# DATABASE CONNECTION
# -----------------------
def get_connection():
    return sqlite3.connect(DATABASE)


# -----------------------
# DATABASE INIT
# -----------------------
def init_db():
    conn = get_connection()
    c = conn.cursor()

    # USERS TABLE
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            password TEXT
        )
    """)

    # STOCK TABLE
    c.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            spare TEXT PRIMARY KEY,
            quantity INTEGER DEFAULT 0
        )
    """)

    # TRANSACTIONS TABLE
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            spare TEXT,
            type TEXT,
            quantity INTEGER,
            customer TEXT,
            warranty TEXT,
            technician TEXT
        )
    """)

    # Insert spares if not exists
    for spare in spares_list:
        c.execute("INSERT OR IGNORE INTO stock (spare, quantity) VALUES (?, ?)", (spare, 0))

    conn.commit()
    conn.close()


init_db()

# -----------------------
# LOGIN
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]

        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE name=? AND password=?", (name, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = name
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid Credentials")

    return render_template("login.html")


# -----------------------
# REGISTER
# -----------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        password = request.form["password"]

        conn = get_connection()
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (name, password) VALUES (?, ?)", (name, password))
            conn.commit()
            conn.close()
            return redirect("/")
        except sqlite3.IntegrityError:
            conn.close()
            return render_template("register.html", error="User already exists")

    return render_template("register.html")


# -----------------------
# DASHBOARD
# -----------------------
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user" not in session:
        return redirect("/")

    conn = get_connection()
    c = conn.cursor()

    if request.method == "POST":

        action = request.form["action"]
        spare = request.form["spare"]
        date = request.form["date"]
        qty = int(request.form["quantity"])

        # Ensure spare exists
        c.execute("SELECT quantity FROM stock WHERE spare=?", (spare,))
        row = c.fetchone()

        if not row:
            conn.close()
            return "Spare not found!"

        current_qty = row[0]

        if action == "inward":
            c.execute("UPDATE stock SET quantity = quantity + ? WHERE spare=?", (qty, spare))

            c.execute("""
                INSERT INTO transactions
                (date, spare, type, quantity, customer, warranty, technician)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, spare, "INWARD", qty, "", "", session["user"]))

        elif action == "consume":

            customer = request.form["customer"]
            warranty = request.form["warranty"]

            if qty > current_qty:
                conn.close()
                return "Not enough stock available!"

            c.execute("UPDATE stock SET quantity = quantity - ? WHERE spare=?", (qty, spare))

            c.execute("""
                INSERT INTO transactions
                (date, spare, type, quantity, customer, warranty, technician)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, spare, "CONSUME", qty, customer, warranty, session["user"]))

        conn.commit()

    stock_df = pd.read_sql_query("SELECT * FROM stock", conn)
    conn.close()

    return render_template(
        "dashboard.html",
        spares=spares_list,
        user=session["user"],
        tables=stock_df.to_html(classes="table table-bordered", index=False)
    )


# -----------------------
# DOWNLOAD STOCK EXCEL
# -----------------------
@app.route("/download_stock")
def download_stock():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM stock", conn)
    conn.close()

    file_name = "stock_report.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)


# -----------------------
# DOWNLOAD CONSUMED EXCEL
# -----------------------
@app.route("/download_consumed")
def download_consumed():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date, spare, quantity, customer, technician, warranty
        FROM transactions
        WHERE type='CONSUME'
    """, conn)
    conn.close()

    file_name = "consumed_spares_report.xlsx"
    df.to_excel(file_name, index=False)

    return send_file(file_name, as_attachment=True)


# -----------------------
# DOWNLOAD PDF
# -----------------------
@app.route("/download_pdf")
def download_pdf():
    conn = get_connection()
    df = pd.read_sql_query("SELECT spare, quantity FROM stock", conn)
    conn.close()

    file_name = "stock_report.pdf"
    pdf = SimpleDocTemplate(file_name)
    elements = []

    data = [["Spare", "Quantity"]] + df.values.tolist()

    table = Table(data)
    table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])

    elements.append(table)
    pdf.build(elements)

    return send_file(file_name, as_attachment=True)


# -----------------------
# LOGOUT
# -----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)