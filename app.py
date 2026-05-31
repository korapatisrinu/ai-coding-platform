from flask import Flask, render_template, request, redirect, session
from flask_mail import Mail, Message
import sqlite3
import subprocess
import bcrypt
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
# =========================================================
# MAIL CONFIG
# =========================================================

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'ssb73888@gmail.com'
app.config['MAIL_PASSWORD'] = 'mdqk twyw xzgd igzq'


mail = Mail(app)

# =========================================================
# DATABASE
# =========================================================

conn = sqlite3.connect("platform.db", check_same_thread=False)
c = conn.cursor()

# USERS
c.execute("""
CREATE TABLE IF NOT EXISTS users(
    username TEXT PRIMARY KEY,
    password BLOB,
    role TEXT,
    rating INTEGER DEFAULT 1200
)
""")

# PROBLEMS
c.execute("""
CREATE TABLE IF NOT EXISTS problems(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT
)
""")

# TEST CASES
c.execute("""
CREATE TABLE IF NOT EXISTS testcases(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER,
    input TEXT,
    output TEXT,
    hidden INTEGER DEFAULT 0
)
""")

# SUBMISSIONS
c.execute("""
CREATE TABLE IF NOT EXISTS submissions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    problem_id INTEGER,
    code TEXT,
    language TEXT,
    verdict TEXT,
    passed INTEGER,
    total INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# =========================================================
# DEFAULT ADMIN
# =========================================================

password = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())

c.execute(
    "INSERT OR IGNORE INTO users(username, password, role) VALUES(?,?,?)",
    ("admin", password, "admin")
)
conn.commit()

def run_code(language, code, input_data):

    try:

        # normalize language
        language = language.lower()

        # ================= PYTHON =================
        if language == "python":

            result = subprocess.run(
                ["python", "-c", code],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )

            return result.stdout.strip(), result.stderr.strip()

        # ================= C++ =================
        elif language == "cpp":

            with open("temp.cpp", "w") as f:
                f.write(code)

            compile_process = subprocess.run(
                ["g++", "temp.cpp", "-o", "temp"],
                capture_output=True,
                text=True
            )

            if compile_process.returncode != 0:
                return "", compile_process.stderr

            run_process = subprocess.run(
                ["./temp"],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )

            return run_process.stdout.strip(), run_process.stderr.strip()

        # ================= JAVA =================
        elif language == "java":

            with open("Main.java", "w") as f:
                f.write(code)

            compile_process = subprocess.run(
                ["javac", "Main.java"],
                capture_output=True,
                text=True
            )

            if compile_process.returncode != 0:
                return "", compile_process.stderr

            run_process = subprocess.run(
                ["java", "Main"],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )

            # remove annoying JAVA_TOOL_OPTIONS message
            stderr = run_process.stderr.replace(
                "Picked up JAVA_TOOL_OPTIONS: -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8",
                ""
            ).strip()

            return run_process.stdout.strip(), stderr

        # ================= NODE =================
        elif language == "js":

            result = subprocess.run(
                ["node", "-e", code],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=5
            )

            return result.stdout.strip(), result.stderr.strip()

        else:
            return "", "Unsupported language"

    except subprocess.TimeoutExpired:
        return "", "Time Limit Exceeded"

    except Exception as e:
        return "", str(e)

# =========================================================
# LOGIN
# =========================================================
@app.route("/", methods=["GET", "POST"])
def login():

    error = ""   # error message variable

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"].encode()

        c.execute("SELECT password, role FROM users WHERE username=?", (username,))
        row = c.fetchone()

        if row and bcrypt.checkpw(password, row[0]):
            session["user"] = username
            session["role"] = row[1]
            return redirect("/dashboard")

        else:
            error = "Username or Password incorrect"

    return render_template("login.html", error=error)
@app.route("/courses")
def courses():
    return render_template("courses.html")


# =========================================================
# PRACTICE PAGE WITH LANGUAGE
# =========================================================
# =========================================================
# PRACTICE PAGE
# =========================================================
@app.route("/practice")
def practice():

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    c.execute("SELECT id, title FROM problems")
    problems = c.fetchall()

    conn.close()

    return render_template("practice.html", problems=problems)


# =========================================================
# PRACTICE PAGE
# =========================================================
# =====================================
# DASHBOARD
# =========================================================
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/")

    # Total problems
    c.execute("SELECT COUNT(*) FROM problems")
    total = c.fetchone()[0]

    # Solved problems (distinct accepted)
    c.execute("""
        SELECT COUNT(DISTINCT problem_id)
        FROM submissions
        WHERE username = ?
        AND verdict = 'Accepted'
    """, (session["user"],))

    solved = c.fetchone()[0] or 0

    pending = total - solved
    if pending < 0:
        pending = 0

    performance = int((solved / total) * 100) if total > 0 else 0

    # Get problem list
    c.execute("SELECT id, title FROM problems")
    problems = c.fetchall()

    print("DEBUG -> Total:", total, "Solved:", solved, "Pending:", pending)

    return render_template(
        "dashboard.html",
        problems=problems,
        solved=solved,
        pending=pending,
        performance=performance
    )

# =========================================================
# ADMIN PANEL
# =========================================================
@app.route("/admin", methods=["GET", "POST"])
def admin():

    if session.get("role") != "admin":
        return "Access Denied"

    msg = ""

      # ================= ADD USER =================
    if "new_user" in request.form:

        username = request.form["new_user"]
        password = request.form["new_pass"]
        role = request.form.get("role", "user")

        hashed_pw = bcrypt.hashpw(
            password.encode(),
            bcrypt.gensalt()
        )

        try:
            c.execute(
                "INSERT INTO users(username, password, role) VALUES(?,?,?)",
                (username, hashed_pw, role)
            )
            conn.commit()
            msg = "User added successfully and Gmail sent"

            # SEND EMAIL
            try:
                email = Message(
                    "SSB Coding Platform Login Details",
                    sender=app.config['MAIL_USERNAME'],
                    recipients=[username]
                )

                email.body = f"""
Hello,

You have been added to the SSB Coding Practice Platform.

Username: {username}
Password: {password}

Login here:
http://127.0.0.1:5000

Enjoy practicing coding!

SSB Training And Placement Pvt Ltd
"""

                mail.send(email)

            except Exception as e:
                print("Email sending failed:", e)

        except sqlite3.IntegrityError:
            msg = "Username already exists"

    # ================= ADD PROBLEM =================
    if "title" in request.form:

        title = request.form["title"]
        description = request.form["description"]

        c.execute(
            "INSERT INTO problems(title, description) VALUES(?,?)",
            (title, description)
        )

        pid = c.lastrowid

        for i in range(1, 6):

            inp = request.form.get(f"input{i}")
            out = request.form.get(f"output{i}")

            if inp and out:
                c.execute(
                    "INSERT INTO testcases(problem_id,input,output) VALUES(?,?,?)",
                    (pid, inp, out)
                )

        conn.commit()
        msg = "Problem added successfully"


    # ================= GET USERS =================
    c.execute("SELECT username, role FROM users")
    users = c.fetchall()


    # ================= GET PROBLEMS =================
    c.execute("SELECT * FROM problems")
    problems = c.fetchall()


    # ================= USER STATISTICS =================
    c.execute("""
        SELECT 
            u.username,
            COUNT(DISTINCT CASE WHEN s.verdict='Accepted' THEN s.problem_id END) AS solved,
            COUNT(s.id) AS submissions,
            SUM(CASE WHEN s.verdict='Accepted' THEN 1 ELSE 0 END) AS accepted,
            SUM(CASE WHEN s.verdict='Wrong Answer' THEN 1 ELSE 0 END) AS wrong
        FROM users u
        LEFT JOIN submissions s
        ON u.username = s.username
        GROUP BY u.username
        ORDER BY solved DESC
    """)

    user_stats = c.fetchall()


    return render_template(
        "admin.html",
        users=users,
        problems=problems,
        user_stats=user_stats,
        msg=msg
    )
@app.route("/delete_problem/<int:pid>")
def delete_problem(pid):

    if session.get("role") != "admin":
        return "Access Denied"

    c.execute("DELETE FROM problems WHERE id=?", (pid,))
    c.execute("DELETE FROM testcases WHERE problem_id=?", (pid,))
    c.execute("DELETE FROM submissions WHERE problem_id=?", (pid,))
    conn.commit()

    return redirect("/admin")
# conster
@app.route("/contest/<int:cid>")
def contest(cid):

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    c.execute("SELECT id, title FROM problems")
    problems = c.fetchall()

    conn.close()

    return render_template("contest.html", problems=problems, cid=cid)


# learder
@app.route("/leaderboard/<int:cid>")
def leaderboard(cid):

    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    c.execute("""
        SELECT u.username, COUNT(DISTINCT s.problem_id) as solved_count
        FROM users u
        LEFT JOIN submissions s
        ON u.username = s.username
        AND s.verdict='Accepted'
        GROUP BY u.username
        ORDER BY solved_count DESC
    """)

    rankings = c.fetchall()

    conn.close()

    return render_template("leaderboard.html", rankings=rankings, cid=cid)
# =========================================================
# PROBLEM PAGE
# =========================================================

@app.route("/problem/<int:pid>")
def problem(pid):

    if "user" not in session:
        return redirect("/")

    c.execute("SELECT * FROM problems WHERE id=?", (pid,))
    problem = c.fetchone()

    if not problem:
        return "Problem not found"

    return render_template("problem.html", problem=problem)
# =========================================================
# EDIT PROBLEM
# =========================================================
@app.route("/edit_problem/<int:pid>", methods=["GET","POST"])
def edit_problem(pid):

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    # ================= UPDATE PROBLEM =================
    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]

        c.execute(
            "UPDATE problems SET title=?, description=? WHERE id=?",
            (title, description, pid)
        )

        # delete old testcases
        c.execute("DELETE FROM testcases WHERE problem_id=?", (pid,))

        # insert new testcases
        for i in range(1,6):

            inp = request.form.get(f"input{i}")
            out = request.form.get(f"output{i}")

            if inp and out:
                c.execute(
                    "INSERT INTO testcases(problem_id,input,output) VALUES(?,?,?)",
                    (pid, inp, out)
                )

        conn.commit()
        conn.close()

        return redirect("/admin")

    # ================= GET PROBLEM =================
    c.execute("SELECT * FROM problems WHERE id=?", (pid,))
    problem = c.fetchone()

    # ================= GET TESTCASES =================
    c.execute("SELECT input, output FROM testcases WHERE problem_id=?", (pid,))
    tests = c.fetchall()

    conn.close()

    return render_template(
        "edit_problem.html",
        problem=problem,
        tests=tests
    )
# admin_submissions
@app.route("/admin_submissions")
def admin_submissions():

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    c.execute("""
        SELECT 
            s.username,
            p.title,
            s.language,
            s.verdict,
            s.created_at
        FROM submissions s
        JOIN problems p
        ON s.problem_id = p.id
        ORDER BY s.created_at DESC
    """)

    submissions = c.fetchall()

    conn.close()

    return render_template("admin_submissions.html", submissions=submissions)

# =========================================================
# RUN — CUSTOM INPUT
# =========================================================
@app.route("/run", methods=["POST"])
def run():

    code = request.form["code"]
    language = request.form["language"]
    stdin = request.form.get("stdin", "").strip()
    pid = request.form.get("pid")

    import sqlite3
    conn = sqlite3.connect("platform.db")
    c = conn.cursor()

    # If user did not give input → use first sample testcase
    if stdin == "" and pid:

        c.execute("""
            SELECT input
            FROM testcases
            WHERE problem_id=? AND hidden=0
            ORDER BY id ASC
            LIMIT 1
        """, (pid,))

        row = c.fetchone()

        if row:
            stdin = row[0]

    conn.close()

    # Fix newline problems
    stdin = stdin.replace("\r\n", "\n").strip() + "\n"

    # Run code
    output, error = run_code(language, code, stdin)

    if error:
        return error

    return output

# =========================================================
# EXECUTE — SAMPLE TESTS
# =========================================================
@app.route("/execute/<int:pid>", methods=["POST"])
def execute(pid):

    code = request.form["code"]
    language = request.form.get("language", "python")

    c.execute(
        "SELECT input, output FROM testcases WHERE problem_id=? AND hidden=0",
        (pid,)
    )
    tests = c.fetchall()

    results = ""

    for i, (inp, expected) in enumerate(tests, 1):

        clean_input = inp.replace("\r\n", "\n")
        if not clean_input.endswith("\n"):
            clean_input += "\n"

        output, error = run_code(language, code, clean_input)

        results += f"Test Case {i}\n"
        results += f"Input:\n{inp}\n"

        if error:
            results += f"Error:\n{error}\n\n"
            continue

        results += f"Expected Output:\n{expected}\n"
        results += f"Your Output:\n{output}\n"

        if output.strip() == expected.strip():
            results += "Result: ✔ Passed\n\n"
        else:
            results += "Result: ✖ Failed\n\n"

    return results

# =========================================================
# SUBMIT — FINAL JUDGE
# =========================================================

@app.route("/submit/<int:pid>", methods=["POST"])
def submit(pid):

    if "user" not in session:
        return "Login required"

    code = request.form["code"]
    language = request.form.get("language", "python")

    c.execute(
        "SELECT input, output FROM testcases WHERE problem_id=?",
        (pid,)
    )
    tests = c.fetchall()

    passed = 0
    total = len(tests)

    for inp, expected in tests:

        clean_input = inp.replace("\r\n", "\n")
        if not clean_input.endswith("\n"):
            clean_input += "\n"

        output, error = run_code(language, code, clean_input)

        if output.strip() == expected.strip():
            passed += 1

    verdict = "Accepted" if passed == total else "Wrong Answer"

    c.execute("""
        INSERT INTO submissions(username, problem_id, code, language, verdict, passed, total)
        VALUES(?,?,?,?,?,?,?)
    """, (session["user"], pid, code, language, verdict, passed, total))

    conn.commit()

    c.execute(
        "SELECT id FROM problems WHERE id > ? ORDER BY id ASC LIMIT 1",
        (pid,)
    )
    next_problem = c.fetchone()
    next_id = next_problem[0] if next_problem else "None"

    return f"{verdict}|{passed}|{total}|{next_id}"
# =========================================================
# RESET USER PROGRESS
# =========================================================
from flask import flash

@app.route("/reset_user/<username>")
def reset_user(username):

    if session.get("role") != "admin":
        return "Access Denied"

    # delete submissions only
    c.execute("DELETE FROM submissions WHERE username=?", (username,))
    conn.commit()

    flash(f"{username} reset successfully!")

    return redirect("/admin")


# =========================================================
# DELETE USER
# =========================================================
@app.route("/delete_user/<username>")
def delete_user(username):

    if session.get("role") != "admin":
        return "Access Denied"

    # delete submissions
    c.execute("DELETE FROM submissions WHERE username=?", (username,))

    # delete user
    c.execute("DELETE FROM users WHERE username=?", (username,))

    conn.commit()

    flash(f"{username} deleted successfully!")

    return redirect("/admin")
# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================================================

if __name__ == "__main__":
    app.run(debug=True)