from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import sqlite3, os, random
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from twilio.rest import Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

# ==============================
# APP CONFIG
# ==============================
app = Flask(__name__)
app.secret_key = "exam_secret"

DB = "database.db"
os.makedirs("uploads", exist_ok=True)

# ==============================
# TWILIO CONFIG (fill real)
# ==============================
TWILIO_SID = "AC728a5e8fa547fb8a226b27558eae16d0"
TWILIO_TOKEN = "9f497ec4d2518273e538142404a32988"
TWILIO_FROM = "+12675516513"
twilio = Client(TWILIO_SID, TWILIO_TOKEN)

def send_sms(to, msg):
    try:
        twilio.messages.create(to=to, from_=TWILIO_FROM, body=msg)
    except:
        pass

# ==============================
# DATABASE
# ==============================
def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()

    # ================= ADMIN =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin(
        username TEXT PRIMARY KEY,
        password TEXT
    )
    """)

    # ================= FACULTY =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS faculty(
        emp_id TEXT PRIMARY KEY,
        name TEXT,
        password TEXT
    )
    """)

    # ================= STUDENTS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS students(
        roll TEXT PRIMARY KEY,
        name TEXT,
        parent TEXT,
        year TEXT,
        branch TEXT,
        section TEXT,
        password TEXT DEFAULT '1234'
    )
    """)

    # ================= EXAMS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_id TEXT,
        year TEXT,
        branch TEXT,
        section TEXT,
        duration INTEGER,
        status TEXT,                -- ACTIVE / INACTIVE
        exam_date TEXT,             -- YYYY-MM-DD
        start_time TEXT,
        end_time TEXT
    )
    """)

    # ================= QUESTIONS (ACTIVE EXAM) =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        question TEXT,
        a TEXT,
        b TEXT,
        c TEXT,
        d TEXT,
        correct TEXT
    )
    """)

    # ================= RESULTS =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results(
        roll TEXT,
        exam_id INTEGER,
        marks INTEGER,
        submitted_at TEXT,
        PRIMARY KEY (roll, exam_id)
    )
    """)

    # ================= EXAM PAPERS (ARCHIVE) =================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_papers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        exam_date TEXT,
        year TEXT,
        branch TEXT,
        section TEXT,
        question TEXT,
        a TEXT,
        b TEXT,
        c TEXT,
        d TEXT,
        correct TEXT
    )
    """)

    # ================= DEFAULT ADMIN =================
    cur.execute("""
    INSERT OR IGNORE INTO admin(username,password)
    VALUES ('admin','admin')
    """)

    con.commit()
    con.close()


init_db()


# ==============================
# AUTO CLOSE EXAMS
# ==============================
def auto_close_exams():
    con = db()
    cur = con.cursor()
    now = datetime.now()

    cur.execute("SELECT * FROM exams WHERE status='ACTIVE'")
    for e in cur.fetchall():
        end = datetime.fromisoformat(e["start_time"]) + timedelta(minutes=e["duration"])
        if now >= end:
            cur.execute("UPDATE exams SET status='INACTIVE' WHERE id=?", (e["id"],))
            cur.execute("DELETE FROM questions WHERE exam_id=?", (e["id"],))

    con.commit()
    con.close()

# =====================================================
# HOME
# =====================================================
@app.route("/")
def home():
    return render_template("home.html")

# =====================================================
# ADMIN
# =====================================================
@app.route("/admin_login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (request.form["username"], request.form["password"])
        )
        if cur.fetchone():
            session["admin"] = True
            return redirect("/admin/dashboard")
    return render_template("admin_login.html")

@app.route("/admin/dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()
    cur = con.cursor()

    # ✅ HANDLE ADD FACULTY
    if request.method == "POST":
        emp_id = request.form["emp_id"]
        name = request.form["name"]
        password = request.form["password"]

        cur.execute("""
            INSERT OR REPLACE INTO faculty (emp_id, name, password)
            VALUES (?,?,?)
        """, (emp_id, name, password))

        con.commit()

    # SHOW FACULTY LIST
    cur.execute("SELECT * FROM faculty")
    faculty = cur.fetchall()
    con.close()

    return render_template("admin_dashboard.html", faculty=faculty)

# ---------- ADMIN UPLOAD STUDENTS ----------
@app.route("/admin/upload_students", methods=["GET", "POST"])
def admin_upload_students():
    if "admin" not in session:
        return redirect("/admin_login")

    if request.method == "POST":
        year = request.form["year"]
        branch = request.form["branch"].lower()
        section = request.form["section"].lower()
        file = request.files["file"]

        df = pd.read_excel(file)

        con = db()
        cur = con.cursor()

        for _, r in df.iterrows():
            cur.execute("""
                INSERT OR REPLACE INTO students
                (roll, name, parent, year, branch, section)
                VALUES (?,?,?,?,?,?)
            """, (
                str(r["roll"]),
                r["name"],
                r["parent"],
                year,
                branch,
                section
            ))

        con.commit()
        con.close()

        return redirect("/admin/students")

    return render_template("admin_upload_students.html")

@app.route("/admin/students")
def admin_students():
    if "admin" not in session:
        return redirect("/admin")

    year = request.args.get("year", "").strip()
    branch = request.args.get("branch", "").strip().lower()
    section = request.args.get("section", "").strip().lower()

    con = db()
    cur = con.cursor()

    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if year:
        query += " AND year=?"
        params.append(year)

    if branch:
        query += " AND LOWER(branch)=?"
        params.append(branch)

    if section:
        query += " AND LOWER(section)=?"
        params.append(section)

    cur.execute(query, params)
    students = cur.fetchall()
    con.close()

    return render_template(
        "admin_students.html",
        students=students,
        year=year,
        branch=branch,
        section=section
    )

@app.route("/admin/delete_student/<roll>")
def admin_delete_student(roll):
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()
    con.execute("DELETE FROM students WHERE roll = ?", (roll,))
    con.commit()
    con.close()

    return redirect("/admin/students")

@app.route("/admin/update_student/<roll>", methods=["POST"])
def admin_update_student(roll):
    if "admin" not in session:
        return redirect("/admin")

    name = request.form["name"]
    year = request.form["year"]
    branch = request.form["branch"].lower()
    section = request.form["section"].lower()
    parent = request.form["parent"]

    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE students
        SET name=?, year=?, branch=?, section=?, parent=?
        WHERE roll=?
    """, (name, year, branch, section, parent, roll))
    con.commit()
    con.close()

    return redirect(request.referrer)


@app.route("/admin/bulk_delete_students", methods=["GET", "POST"])
def admin_bulk_delete_students():
    if "admin" not in session:
        return redirect("/admin")

    if request.method == "GET":
        return render_template("admin_bulk_delete.html")

    year = request.form["year"].strip()
    branch = request.form["branch"].strip().lower()
    section = request.form["section"].strip().lower()

    con = db()
    cur = con.cursor()

    cur.execute("""
        DELETE FROM students
        WHERE year=? AND lower(branch)=? AND lower(section)=?
    """, (year, branch, section))

    con.commit()
    con.close()

    return redirect("/admin/students")


@app.route("/admin/results")
def admin_results():
    if "admin" not in session:
        return redirect("/admin_login")

    year = request.args.get("year")
    branch = request.args.get("branch")
    section = request.args.get("section")
    date = request.args.get("date")

    query = """
        SELECT r.roll, s.name, s.year, s.branch, s.section,
               r.marks, r.submit_time
        FROM results r
        JOIN students s ON r.roll=s.roll
        WHERE 1=1
    """
    params = []

    if year:
        query += " AND s.year=?"; params.append(year)
    if branch:
        query += " AND s.branch=?"; params.append(branch)
    if section:
        query += " AND s.section=?"; params.append(section)
    if date:
        query += " AND DATE(r.submit_time)=?"; params.append(date)

    con = db()
    rows = con.execute(query, params).fetchall()
    con.close()

    return render_template(
        "admin_results.html",
        rows=rows,
        year=year,
        branch=branch,
        section=section,
        date=date
    )

# =====================================================
# FACULTY
# =====================================================
@app.route("/faculty", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        con = db()
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM faculty WHERE emp_id=? AND password=?",
            (request.form["emp"], request.form["password"])
        )
        if cur.fetchone():
            session["emp"] = request.form["emp"]
            return redirect("/faculty/dashboard")
    return render_template("faculty_login.html")


@app.route("/faculty/dashboard")
def faculty_dashboard():
    if "emp" not in session:
        return redirect("/faculty")

    auto_close_exams()

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT e.*,
        (SELECT COUNT(*) FROM students s
         WHERE s.year=e.year AND s.branch=e.branch AND s.section=e.section) AS student_count,
        (SELECT COUNT(*) FROM questions q WHERE q.exam_id=e.id) AS question_count
        FROM exams e WHERE emp_id=?
        ORDER BY id DESC
    """, (session["emp"],))

    return render_template("faculty_dashboard.html", exams=cur.fetchall())

@app.route("/faculty/create_exam", methods=["GET","POST"])
def create_exam():
    if "emp" not in session:
        return redirect("/faculty")

    if request.method == "POST":
        con = db()
        con.execute("""
            INSERT INTO exams
            (emp_id, year, branch, section, duration, status)
            VALUES (?,?,?,?,?,'INACTIVE')
        """, (
            session["emp"],
            request.form["year"],
            request.form["branch"].lower(),
            request.form["section"].lower(),
            int(request.form["duration"])
        ))
        con.commit()
        con.close()
        return redirect("/faculty/dashboard")

    return render_template("create_exam.html")

@app.route("/faculty/get_students")
def faculty_get_students():
    if "emp" not in session:
        return ""

    year = request.args.get("year")
    branch = request.args.get("branch")
    section = request.args.get("section")

    con = db()                 # ✅ create connection
    cur = con.cursor()         # ✅ create cursor

    cur.execute("""
        SELECT roll, name, parent
        FROM students
        WHERE year=? AND branch=? AND section=?
        ORDER BY roll
    """, (year, branch, section))

    students = cur.fetchall()
    con.close()

    return render_template(
        "faculty_students_table.html",
        students=students
    )

@app.route("/faculty/import_questions/<int:exam_id>", methods=["POST"])
def import_questions(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    file = request.files.get("file")
    if not file:
        return "❌ No file selected"

    df = pd.read_excel(file)

    con = db()
    cur = con.cursor()

    # Clear old questions (important)
    cur.execute("DELETE FROM questions WHERE exam_id=?", (exam_id,))

    for _, r in df.iterrows():
        cur.execute("""
            INSERT INTO questions
            (exam_id, question, a, b, c, d, correct)
            VALUES (?,?,?,?,?,?,?)
        """, (
            exam_id,
            r["question"],
            r["a"],
            r["b"],
            r["c"],
            r["d"],
            r["correct"].lower()
        ))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")

@app.route("/faculty/start_exam/<int:exam_id>")
def faculty_start_exam(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    con = db()
    cur = con.cursor()

    # ✅ Ensure questions exist
    cur.execute("SELECT COUNT(*) FROM questions WHERE exam_id=?", (exam_id,))
    if cur.fetchone()[0] == 0:
        con.close()
        return "❌ Please import questions before starting exam"

    # ✅ Start exam
    cur.execute("""
        UPDATE exams
        SET status='ACTIVE',
            start_time=?
        WHERE id=? AND emp_id=?
    """, (
        datetime.now().isoformat(),
        exam_id,
        session["emp"]
    ))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")

@app.route("/faculty/delete_exam/<int:exam_id>")
def faculty_delete_exam(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    con = db()
    cur = con.cursor()

    # Only allow delete if exam is INACTIVE
    cur.execute("SELECT status FROM exams WHERE id=?", (exam_id,))
    exam = cur.fetchone()

    if not exam or exam["status"] == "ACTIVE":
        con.close()
        return redirect("/faculty/dashboard")

    # Delete related data
    cur.execute("DELETE FROM questions WHERE exam_id=?", (exam_id,))
    cur.execute("DELETE FROM results WHERE exam_id=?", (exam_id,))
    cur.execute("DELETE FROM exam_papers WHERE exam_id=?", (exam_id,))
    cur.execute("DELETE FROM exams WHERE id=?", (exam_id,))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")


@app.route("/faculty/stop_exam/<int:exam_id>")
def stop_exam(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    con = db()
    cur = con.cursor()

    # 🔎 Get exam details
    cur.execute("""
        SELECT year, branch, section, exam_date
        FROM exams
        WHERE id=?
    """, (exam_id,))
    exam = cur.fetchone()

    if not exam:
        con.close()
        return redirect("/faculty/dashboard")

    # 📦 Fetch all questions of this exam
    cur.execute("""
        SELECT question, a, b, c, d, correct
        FROM questions
        WHERE exam_id=?
    """, (exam_id,))
    questions = cur.fetchall()

    # 🗂 Move questions → exam_papers (for downloads)
    for q in questions:
        cur.execute("""
            INSERT INTO exam_papers (
                exam_id,
                year, branch, section, exam_date,
                question, a, b, c, d, correct
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            exam_id,
            exam["year"],
            exam["branch"],
            exam["section"],
            exam["exam_date"],
            q["question"],
            q["a"], q["b"], q["c"], q["d"],
            q["correct"]
        ))

    # ❌ Delete active questions (exam disappears for students)
    cur.execute("DELETE FROM questions WHERE exam_id=?", (exam_id,))

    # ⛔ Close the exam
    cur.execute("""
        UPDATE exams
        SET status='INACTIVE'
        WHERE id=?
    """, (exam_id,))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")


@app.route("/faculty/results/<int:exam_id>")
def faculty_results(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    con = db()
    cur = con.cursor()

    # Exam details
    cur.execute("SELECT * FROM exams WHERE id=?", (exam_id,))
    exam = cur.fetchone()

    # Results
    cur.execute("""
        SELECT r.roll, s.name, r.marks, r.submit_time
        FROM results r
        JOIN students s ON r.roll = s.roll
        WHERE r.exam_id=?
        ORDER BY r.marks DESC
    """, (exam_id,))
    rows = cur.fetchall()

    # Excel download
    if request.args.get("download"):
        df = pd.DataFrame(rows, columns=[
            "Roll", "Name", "Marks", "Submitted Time"
        ])
        file = f"results_exam_{exam_id}.xlsx"
        df.to_excel(file, index=False)
        return send_file(file, as_attachment=True)

    date = exam["end_time"][:10] if exam["end_time"] else ""

    return render_template(
        "faculty_results.html",
        exam=exam,
        results=rows,
        date=date
    )


# ---------- MONITOR ----------
@app.route("/faculty/monitor/<int:exam_id>")
def faculty_monitor(exam_id):
    if "emp" not in session:
        return redirect("/faculty")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT * FROM exams WHERE id=? AND emp_id=?", (exam_id, session["emp"]))
    exam = cur.fetchone()

    if not exam:
        con.close()
        return redirect("/faculty/dashboard")

    cur.execute("""
        SELECT COUNT(*) FROM students
        WHERE year=? AND branch=? AND section=?
    """, (exam["year"], exam["branch"], exam["section"]))
    total_students = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM results WHERE exam_id=?", (exam_id,))
    submitted = cur.fetchone()[0]

    con.close()

    return render_template(
        "monitor.html",
        exam=exam,
        total_students=total_students,
        submitted=submitted,
        writing=total_students - submitted
    )

# =====================================================
# STUDENT
# =====================================================
@app.route("/student", methods=["GET","POST"])
def student_login():
    if request.method == "POST":
        roll = request.form["roll"]
        password = request.form["password"]

        con = db()
        cur = con.cursor()
        cur.execute("""
            SELECT * FROM students
            WHERE roll=? AND password=?
        """, (roll, password))
        s = cur.fetchone()
        con.close()

        if s:
            session["roll"] = roll
            return redirect("/student/dashboard")
        else:
            return render_template("student_login.html",
                                   error="Invalid roll number or password")

    return render_template("student_login.html")

@app.route("/student/change_password", methods=["GET", "POST"])
def student_change_password():
    if request.method == "POST":
        roll = request.form["roll"]
        old = request.form["old_password"]
        new = request.form["new_password"]

        con = db()
        cur = con.cursor()

        cur.execute(
            "SELECT * FROM students WHERE roll=? AND password=?",
            (roll, old)
        )
        if not cur.fetchone():
            con.close()
            return render_template(
                "student_password_change.html",
                error="Old password is incorrect"
            )

        cur.execute(
            "UPDATE students SET password=? WHERE roll=?",
            (new, roll)
        )
        con.commit()
        con.close()

        return redirect("/student")

    return render_template("student_password_change.html")


@app.route("/student/dashboard")
def student_dashboard():
    if "roll" not in session:
        return redirect("/student")

    con = db()
    cur = con.cursor()

    # 1️⃣ Get logged-in student details
    cur.execute("""
        SELECT year, branch, section
        FROM students
        WHERE roll=?
    """, (session["roll"],))
    s = cur.fetchone()

    if not s:
        con.close()
        return redirect("/student")

    # 2️⃣ FIND ACTIVE EXAM (THIS IS WHERE YOUR QUERY GOES ✅)
    cur.execute("""
        SELECT * FROM exams
        WHERE status='ACTIVE'
        AND year=?
        AND LOWER(branch)=LOWER(?)
        AND LOWER(section)=LOWER(?)
    """, (s["year"], s["branch"], s["section"]))

    active_exam = cur.fetchone()

    # 3️⃣ Get previous exam papers (PDF download section)
    cur.execute("""
        SELECT DISTINCT exam_date
        FROM exam_papers
        WHERE year=?
        AND LOWER(branch)=LOWER(?)
        AND LOWER(section)=LOWER(?)
        ORDER BY exam_date DESC
    """, (s["year"], s["branch"], s["section"]))

    past_dates = cur.fetchall()

    con.close()

    # 4️⃣ Send data to dashboard
    return render_template(
        "student_dashboard.html",
        active_exam=active_exam,
        past_dates=past_dates
    )


@app.route("/exam/<int:exam_id>", methods=["GET", "POST"])
def exam(exam_id):
    if "roll" not in session:
        return redirect("/student")

    con = db()
    cur = con.cursor()

    # Prevent reattempt
    cur.execute(
        "SELECT 1 FROM results WHERE roll=? AND exam_id=?",
        (session["roll"], exam_id)
    )
    if cur.fetchone():
        con.close()
        return redirect("/student/dashboard")

    # ================= GET → SHOW QUESTIONS =================
    if request.method == "GET":
        cur.execute(
            "SELECT * FROM questions WHERE exam_id=?",
            (exam_id,)
        )
        questions = cur.fetchall()

        random.shuffle(questions)
        session["q_order"] = [q["id"] for q in questions]

        con.close()
        return render_template("exam.html", questions=questions)

    # ================= POST → SUBMIT EXAM =================
    marks = 0
    for qid in session.get("q_order", []):
        cur.execute("SELECT correct FROM questions WHERE id=?", (qid,))
        correct = cur.fetchone()["correct"]

        if request.form.get(str(qid)) == correct:
            marks += 1

    # Save result
    cur.execute("""
        INSERT INTO results (roll, exam_id, marks, submit_time)
        VALUES (?, ?, ?, datetime('now'))
    """, (
        session["roll"],
        exam_id,
        marks
    ))

    # Get parent mobile
    cur.execute(
        "SELECT parent FROM students WHERE roll=?",
        (session["roll"],)
    )
    parent_mobile = cur.fetchone()["parent"]

    con.commit()
    con.close()

    # ✅ SEND SMS (ONLY 2 ARGUMENTS)
    send_sms(
        parent_mobile,
        f"Your child {session['roll']} completed the exam. Score: {marks}"
    )

    # ✅ SHOW RESULT PAGE
    return render_template(
        "result.html",
        marks=marks
    )


@app.route("/student/download_paper/<exam_date>")
def download_exam_pdf(exam_date):
    if "roll" not in session:
        return redirect("/student")

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT year, branch, section
        FROM students WHERE roll=?
    """, (session["roll"],))
    s = cur.fetchone()

    cur.execute("""
        SELECT question, a, b, c, d, correct
        FROM exam_papers
        WHERE year=? AND branch=? AND section=? AND exam_date=?
    """, (s["year"], s["branch"], s["section"], exam_date))

    qs = cur.fetchall()
    con.close()

    if not qs:
        return redirect("/student/dashboard")

    # ---- PDF ----
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from io import BytesIO

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    text = pdf.beginText(40, 800)

    text.textLine(f"Exam Paper – {exam_date}")
    text.textLine("")

    for i, q in enumerate(qs, 1):
        text.textLine(f"Q{i}. {q['question']}")
        text.textLine(f"A) {q['a']}")
        text.textLine(f"B) {q['b']}")
        text.textLine(f"C) {q['c']}")
        text.textLine(f"D) {q['d']}")
        text.textLine(f"Answer: {q['correct'].upper()}")
        text.textLine("")

    pdf.drawText(text)
    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Exam_{exam_date}.pdf"
    )

# =====================================================
# ANSWER KEY DOWNLOAD
# =====================================================
@app.route("/faculty/answer_key/<int:exam_id>")
def answer_key_download(exam_id):
    if "emp" not in session and "admin" not in session:
        return redirect("/")

    con = db()
    cur = con.cursor()

    cur.execute("SELECT * FROM exams WHERE id=?", (exam_id,))
    exam = cur.fetchone()

    cur.execute("""
        SELECT COUNT(*) FROM students
        WHERE year=? AND branch=? AND section=?
    """, (exam["year"], exam["branch"], exam["section"]))
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM results WHERE exam_id=?", (exam_id,))
    submitted = cur.fetchone()[0]

    if exam["status"] == "ACTIVE" and submitted < total:
        return "❌ Exam still running"

    cur.execute("""
        SELECT question,a,b,c,d,correct
        FROM questions WHERE exam_id=?
    """, (exam_id,))

    df = pd.DataFrame(cur.fetchall(),
                      columns=["Question","A","B","C","D","Correct"])

    out = BytesIO()
    df.to_excel(out, index=False)
    out.seek(0)

    return send_file(out, as_attachment=True,
                     download_name=f"answer_key_exam_{exam_id}.xlsx")

# =====================================================
# LOGOUT
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(debug=True)
