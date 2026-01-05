
from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3, os, random
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
from twilio.rest import Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# =========================
# APP CONFIG
# =========================
app = Flask(__name__)
app.secret_key = "your_secret_key"


DB = "database.db"   # ✅ FIX 1: DB defined ONCE

os.makedirs("uploads", exist_ok=True)

# =========================
# DATABASE CONNECTION (SINGLE, SAFE VERSION)
# =========================
def db():
    con = sqlite3.connect(
        DB,
        timeout=30,
        check_same_thread=False
    )
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


# =========================
# TWILIO CONFIG
# =========================
import os

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

TWILIO_FROM = "+12355656"
twilio = Client(TWILIO_SID, TWILIO_TOKEN)

def send_sms(to, msg):
    try:
        twilio.messages.create(to=to, from_=TWILIO_FROM, body=msg)
    except:
        pass

# =========================
# INIT DATABASE
# =========================
def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS admin(
        username TEXT PRIMARY KEY,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS faculty(
        emp_id TEXT PRIMARY KEY,
        name TEXT,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS students(
        roll TEXT PRIMARY KEY,
        name TEXT,
        parent TEXT,
        year TEXT,
        branch TEXT,
        section TEXT,
        password TEXT DEFAULT '1234'
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS exams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_id TEXT,
        year TEXT,
        branch TEXT,
        section TEXT,
        duration INTEGER,
        status TEXT,
        start_time TEXT,
        exam_date TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        question TEXT,
        a TEXT,b TEXT,c TEXT,d TEXT,
        correct TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS results(
        roll TEXT,
        exam_id INTEGER,
        marks INTEGER,
        submit_time TEXT,
        PRIMARY KEY(roll,exam_id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS attendance(
        exam_id INTEGER,
        roll TEXT,
        status TEXT,
        PRIMARY KEY(exam_id,roll)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS exam_papers(
        exam_id INTEGER,
        year TEXT,
        branch TEXT,
        section TEXT,
        exam_date TEXT,
        question TEXT,a TEXT,b TEXT,c TEXT,d TEXT,correct TEXT
    )""")

    cur.execute("""
        INSERT OR IGNORE INTO admin(username,password)
        VALUES('admin','admin')
    """)

    con.commit()
    con.close()

init_db()

# =========================
# AUTO CLOSE EXAMS
# =========================
def auto_close_exams():
    con = db()
    cur = con.cursor()
    now = datetime.now()

    for e in cur.execute("SELECT * FROM exams WHERE status='ACTIVE'"):
        end = datetime.fromisoformat(e["start_time"]) + timedelta(minutes=e["duration"])
        if now >= end:
            cur.execute("UPDATE exams SET status='INACTIVE' WHERE id=?", (e["id"],))

    con.commit()
    con.close()

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return render_template("home.html")

# =========================
# ADMIN
# =========================
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        con = db()
        admin = con.execute(
            "SELECT * FROM admin WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        con.close()

        if admin:
            session["admin"] = username
            return redirect("/admin/dashboard")
        else:
            return "❌ Invalid admin credentials"

    return render_template("admin_login.html")


@app.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()
    faculty = con.execute("SELECT * FROM faculty").fetchall()
    students = con.execute("SELECT * FROM students").fetchall()
    exams = con.execute("SELECT * FROM exams").fetchall()
    con.close()

    return render_template(
        "admin_dashboard.html",
        faculty=faculty,
        students=students,
        exams=exams
    )

@app.route("/admin/add_faculty", methods=["POST"])
def add_faculty():
    if "admin" not in session:
        return redirect("/admin_login")

    emp_id = request.form.get("emp_id")
    name = request.form.get("name")
    password = request.form.get("password")

    if not emp_id or not name or not password:
        return "❌ All fields are required"

    con = db()

    exists = con.execute(
        "SELECT 1 FROM faculty WHERE emp_id=?",
        (emp_id,)
    ).fetchone()

    if exists:
        con.close()
        return "❌ Faculty already exists"

    con.execute(
        "INSERT INTO faculty (emp_id, name, password) VALUES (?,?,?)",
        (emp_id, name, password)
    )

    con.commit()
    con.close()

    return redirect("/admin/dashboard")

@app.route("/admin/delete_faculty/<emp_id>")
def delete_faculty(emp_id):
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()
    con.execute("DELETE FROM faculty WHERE emp_id=?", (emp_id,))
    con.commit()
    con.close()

    return redirect("/admin/dashboard")

@app.route("/admin/upload_students", methods=["GET", "POST"])
def upload_students():
    if "admin" not in session:
        return redirect("/admin_login")

    if request.method == "POST":
        year = request.form["year"]
        branch = request.form["branch"]
        section = request.form["section"]
        file = request.files["file"]

        # Check if section already exists
        con = db()
        existing = con.execute("""
            SELECT COUNT(*) FROM students
            WHERE year=? AND branch=? AND section=?
        """, (year, branch, section)).fetchone()[0]

        if existing > 0:
            con.close()
            return "❌ Students already uploaded for this Year + Branch + Section. Please bulk delete first."

        # Read Excel
        df = pd.read_excel(file)

        for _, row in df.iterrows():
            con.execute("""
                INSERT INTO students
                (roll, name, parent, year, branch, section)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row["roll"],
                row["name"],
                str(row["parent"]),
                year,
                branch,
                section
            ))

        con.commit()
        con.close()

        return redirect("/admin/dashboard")

    return render_template("admin_upload_students.html")

@app.route("/admin/view_students", methods=["GET"])
def admin_view_students():
    if "admin" not in session:
        return redirect("/admin_login")

    year = request.args.get("year")
    branch = request.args.get("branch")
    section = request.args.get("section")

    con = db()

    query = "SELECT * FROM students WHERE 1=1"
    params = []

    if year:
        query += " AND year=?"
        params.append(year)

    if branch:
        query += " AND branch=?"
        params.append(branch)

    if section:
        query += " AND section=?"
        params.append(section)

    students = con.execute(query, params).fetchall()
    con.close()

    return render_template(
        "admin_view_students.html",
        students=students,
        year=year,
        branch=branch,
        section=section
    )

@app.route("/admin/update_student/<roll>", methods=["POST"])
def update_student(roll):
    if "admin" not in session:
        return redirect("/admin_login")

    name = request.form.get("name")
    parent = request.form.get("parent")
    year = request.form.get("year")
    branch = request.form.get("branch")
    section = request.form.get("section")

    con = db()
    con.execute("""
        UPDATE students
        SET name=?, parent=?, year=?, branch=?, section=?
        WHERE roll=?
    """, (name, parent, year, branch, section, roll))

    con.commit()
    con.close()

    return redirect("/admin/view_students")

@app.route("/admin/delete_student/<roll>")
def delete_student(roll):
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()
    con.execute("DELETE FROM students WHERE roll=?", (roll,))
    con.commit()
    con.close()

    return redirect("/admin/view_students")


@app.route("/admin/bulk_delete", methods=["GET", "POST"])
def bulk_delete_students():
    if "admin" not in session:
        return redirect("/admin_login")

    if request.method == "POST":
        year = request.form.get("year")
        branch = request.form.get("branch")
        section = request.form.get("section")

        if not year or not branch:
            return "❌ Year and Branch are required"

        con = db()

        if section:
            con.execute("""
                DELETE FROM students
                WHERE year=? AND branch=? AND section=?
            """, (year, branch, section))
        else:
            # LE students → no section
            con.execute("""
                DELETE FROM students
                WHERE year=? AND branch=?
            """, (year, branch))

        con.commit()
        con.close()

        return redirect("/admin/view_students")

    return render_template("admin_bulk_delete.html")

@app.route("/admin/results")
def admin_results():
    if "admin" not in session:
        return redirect("/admin_login")

    year = request.args.get("year", "")
    branch = request.args.get("branch", "")
    section = request.args.get("section", "")
    date = request.args.get("date", "")

    query = """
        SELECT r.roll, s.name, s.year, s.branch, s.section,
               r.marks, r.submit_time
        FROM results r
        JOIN students s ON r.roll=s.roll
        JOIN exams e ON r.exam_id=e.id
        WHERE 1=1
    """
    params = []

    if year:
        query += " AND s.year=?"
        params.append(year)
    if branch:
        query += " AND s.branch=?"
        params.append(branch)
    if section:
        query += " AND s.section=?"
        params.append(section)
    if date:
        query += " AND DATE(r.submit_time)=?"
        params.append(date)

    con = db()
    rows = con.execute(query, params).fetchall()
    con.close()

    return render_template("admin_results.html", rows=rows)


@app.route("/admin/reset_student_password/<roll>", methods=["GET", "POST"])
def admin_reset_student_password(roll):

    # 🔐 Admin protection
    if "admin" not in session:
        return redirect("/admin_login")

    con = db()

    student = con.execute(
        "SELECT roll, name FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    if not student:
        con.close()
        return "❌ Student not found"

    if request.method == "POST":
        new_password = request.form["password"]

        con.execute(
            "UPDATE students SET password=? WHERE roll=?",
            (new_password, roll)
        )
        con.commit()
        con.close()

        return redirect("/admin/view_students")

    con.close()

    return render_template(
        "admin_reset_student_password.html",
        student=student
    )

@app.route("/admin/attendance")
def admin_attendance():
    if "admin" not in session:
        return redirect("/admin_login")

    year = request.args.get("year")
    branch = request.args.get("branch")
    section = request.args.get("section")
    date = request.args.get("date")

    query = """
        SELECT
            s.roll,
            s.name,
            s.year,
            s.branch,
            s.section,
            e.exam_date,
            r.marks,
            a.status
        FROM attendance a
        JOIN students s ON a.roll = s.roll
        JOIN exams e ON a.exam_id = e.id
        LEFT JOIN results r
            ON r.roll = s.roll AND r.exam_id = e.id
        WHERE 1=1
    """
    params = []

    if year:
        query += " AND s.year=?"
        params.append(year)

    if branch:
        query += " AND s.branch=?"
        params.append(branch)

    if section and section != "all":
        query += " AND s.section=?"
        params.append(section)

    if date:
        query += " AND e.exam_date=?"
        params.append(date)

    con = db()
    rows = con.execute(query, params).fetchall()
    con.close()

    return render_template("admin_attendance.html", rows=rows)

#================================
# FACULTY LOGIN
#===================================
@app.route("/faculty_login", methods=["GET", "POST"])
def faculty_login():
    if request.method == "POST":
        emp = request.form["emp"]
        pwd = request.form["password"]

        con = db()
        f = con.execute(
            "SELECT * FROM faculty WHERE emp_id=? AND password=?",
            (emp, pwd)
        ).fetchone()
        con.close()

        if f:
            session["faculty"] = emp   # 🔴 MUST EXIST
            return redirect("/faculty/dashboard")

    return render_template("faculty_login.html")


@app.route("/faculty/dashboard")
def faculty_dashboard():
    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()

    exams = con.execute("""
        SELECT e.*,
               (
                   SELECT COUNT(*)
                   FROM students
                   WHERE year = e.year
                     AND branch = e.branch
                     AND section = e.section
               ) AS student_count
        FROM exams e
        ORDER BY e.id DESC
    """).fetchall()

    con.close()

    return render_template(
        "faculty_dashboard.html",
        exams=exams,
        current_faculty=session["faculty"]
    )

@app.route("/faculty/create_exam", methods=["GET", "POST"])
def create_exam():
    if "faculty" not in session:
        return redirect("/faculty_login")

    students = []
    error = ""

    if request.method == "POST":
        year = request.form["year"]
        branch = request.form["branch"]
        section = request.form.get("section", "na")

        # LE has no section
        if branch == "le":
            section = "na"

        duration = request.form.get("duration")

        con = db()

        # 🔴 BLOCK IF ACTIVE EXAM EXISTS
        active = con.execute("""
            SELECT COUNT(*) FROM exams
            WHERE year=? AND branch=? AND section=? AND status='ACTIVE'
        """, (year, branch, section)).fetchone()[0]

        if active > 0:
            con.close()
            error = "❌ An exam is already ACTIVE for this Year / Branch / Section"
            return render_template(
                "faculty_create_exam.html",
                error=error
            )

        # Load students
        students = con.execute("""
            SELECT roll, name FROM students
            WHERE year=? AND branch=? AND section=?
        """, (year, branch, section)).fetchall()

        # Preview students
        if "preview" in request.form:
            con.close()
            if not students:
                error = "❌ No students found for this section"
            return render_template(
                "faculty_create_exam.html",
                students=students,
                year=year,
                branch=branch,
                section=section,
                error=error
            )

        # Do not create exam if no students
        if not students:
            con.close()
            return "❌ Cannot create exam without students"

        # Create exam (INACTIVE first)
        con.execute("""
            INSERT INTO exams
            (emp_id, year, branch, section, duration, status, start_time, exam_date)
            VALUES (?, ?, ?, ?, ?, 'INACTIVE', '', DATE('now'))
        """, (
            session["faculty"], year, branch, section, duration
        ))

        con.commit()
        con.close()

        return redirect("/faculty/dashboard")

    return render_template("faculty_create_exam.html")

@app.route("/faculty/upload_questions/<int:exam_id>", methods=["GET", "POST"])
def upload_questions(exam_id):
    if "faculty" not in session:
        return redirect("/faculty_login")

    if request.method == "POST":
        file = request.files["file"]
        df = pd.read_excel(file)

        con = db()
        for _, r in df.iterrows():
            con.execute("""
                INSERT INTO questions
                (exam_id, question, a, b, c, d, correct)
                VALUES (?,?,?,?,?,?,?)
            """, (
                exam_id,
                r["question"], r["a"], r["b"],
                r["c"], r["d"], r["correct"]
            ))
        con.commit()
        con.close()

        return redirect("/faculty/dashboard")

    return render_template("faculty_upload_questions.html", exam_id=exam_id)

@app.route("/faculty/start_exam/<int:exam_id>")
def start_exam(exam_id):
    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()

    # Check questions count
    qcount = con.execute(
        "SELECT COUNT(*) FROM questions WHERE exam_id=?",
        (exam_id,)
    ).fetchone()[0]

    if qcount == 0:
        con.close()
        return "❌ Cannot start exam without importing questions"

    # Start exam
    con.execute("""
        UPDATE exams
        SET status='ACTIVE', start_time=DATETIME('now')
        WHERE id=?
    """, (exam_id,))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")

@app.route("/faculty/monitor/<int:exam_id>")
def monitor_exam(exam_id):
    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()

    # Get exam details
    exam = con.execute(
        "SELECT * FROM exams WHERE id=?",
        (exam_id,)
    ).fetchone()

    # Total students for this exam section
    total = con.execute("""
        SELECT COUNT(*) FROM students
        WHERE year=? AND branch=? AND section=?
    """, (exam["year"], exam["branch"], exam["section"])).fetchone()[0]

    # Submitted count
    submitted = con.execute("""
        SELECT COUNT(*) FROM results
        WHERE exam_id=?
    """, (exam_id,)).fetchone()[0]

    writing = total - submitted

    # Student-wise status
    students = con.execute("""
        SELECT s.roll, s.name,
               CASE
                   WHEN r.roll IS NOT NULL THEN 'SUBMITTED'
                   ELSE 'WRITING'
               END AS status,
               r.marks
        FROM students s
        LEFT JOIN results r
            ON s.roll = r.roll AND r.exam_id=?
        WHERE s.year=? AND s.branch=? AND s.section=?
        ORDER BY s.roll
    """, (
        exam_id,
        exam["year"], exam["branch"], exam["section"]
    )).fetchall()

    con.close()

    return render_template(
        "faculty_monitor.html",
        exam=exam,
        students=students,
        total=total,
        submitted=submitted,
        writing=writing
    )

@app.route("/faculty/results", methods=["GET"])
def faculty_results():

    # 🔐 Login protection
    if "faculty" not in session:
        return redirect("/faculty_login")

    year = request.args.get("year", "")
    branch = request.args.get("branch", "")
    section = request.args.get("section", "")
    date = request.args.get("date", "")

    con = db()

    query = """
        SELECT r.roll, s.name, r.marks, r.submit_time,
               e.year, e.branch, e.section, e.id AS exam_id
        FROM results r
        JOIN students s ON s.roll = r.roll
        JOIN exams e ON e.id = r.exam_id
        WHERE e.emp_id = ?
    """
    params = [session["faculty"]]

    if year:
        query += " AND e.year=?"
        params.append(year)
    if branch:
        query += " AND e.branch=?"
        params.append(branch)
    if section:
        query += " AND e.section=?"
        params.append(section)
    if date:
        query += " AND DATE(r.submit_time)=?"
        params.append(date)

    query += " ORDER BY r.submit_time DESC"

    rows = con.execute(query, params).fetchall()
    con.close()

    return render_template(
        "faculty_results.html",
        rows=rows,
        fy=year,
        fb=branch,
        fs=section,
        fd=date
    )


@app.route("/faculty/export_results")
def export_results():

    if "faculty" not in session:
        return redirect("/faculty_login")

    year = request.args.get("year", "")
    branch = request.args.get("branch", "")
    section = request.args.get("section", "")
    date = request.args.get("date", "")

    con = db()

    query = """
        SELECT r.roll, s.name, r.marks, r.submit_time,
               e.year, e.branch, e.section
        FROM results r
        JOIN students s ON s.roll = r.roll
        JOIN exams e ON e.id = r.exam_id
        WHERE e.emp_id = ?
    """
    params = [session["faculty"]]

    if year:
        query += " AND e.year=?"; params.append(year)
    if branch:
        query += " AND e.branch=?"; params.append(branch)
    if section:
        query += " AND e.section=?"; params.append(section)
    if date:
        query += " AND DATE(r.submit_time)=?"; params.append(date)

    rows = con.execute(query, params).fetchall()
    con.close()

    df = pd.DataFrame(rows, columns=[
        "Roll", "Name", "Marks", "Submitted At",
        "Year", "Branch", "Section"
    ])

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="exam_results.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.route("/faculty/end_exam/<int:exam_id>")
def end_exam(exam_id):

    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()

    # Only creator can end
    exam = con.execute("""
        SELECT id FROM exams
        WHERE id=? AND emp_id=? AND status='ACTIVE'
    """, (exam_id, session["faculty"])).fetchone()

    if not exam:
        con.close()
        return "❌ You cannot end this exam"

    con.execute("""
        UPDATE exams 
        SET status='INACTIVE'
        WHERE id=?
    """, (exam_id,))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")


@app.route("/faculty/delete_exam/<int:exam_id>")
def delete_exam(exam_id):

    # 🔐 Login protection
    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()

    # 🔍 Check exam ownership
    exam = con.execute("""
        SELECT status 
        FROM exams 
        WHERE id=? AND emp_id=?
    """, (exam_id, session["faculty"])).fetchone()

    if not exam:
        con.close()
        return "❌ You are not allowed to delete this exam"

    # ❌ BLOCK ONLY ACTIVE EXAMS
    if exam["status"] == "ACTIVE":
        con.close()
        return "❌ Stop the exam before deleting"

    # ✅ DELETE EVERYTHING (SAFE)
    con.execute("DELETE FROM questions WHERE exam_id=?", (exam_id,))
    con.execute("DELETE FROM results WHERE exam_id=?", (exam_id,))
    con.execute("DELETE FROM attendance WHERE exam_id=?", (exam_id,))
    con.execute("DELETE FROM exam_papers WHERE exam_id=?", (exam_id,))
    con.execute("DELETE FROM exams WHERE id=?", (exam_id,))

    con.commit()
    con.close()

    return redirect("/faculty/dashboard")


@app.route("/faculty/attendance/<int:exam_id>")
def attendance_report(exam_id):
    if "faculty" not in session:
        return redirect("/faculty_login")

    con = db()
    rows = con.execute("""
        SELECT s.roll,s.name,
        IFNULL(a.status,'ABSENT') AS status
        FROM students s
        LEFT JOIN attendance a
        ON s.roll=a.roll AND a.exam_id=?
    """, (exam_id,)).fetchall()
    con.close()

    return render_template("attendance.html", rows=rows)



#==========================
# STUDENT LOGIN
#==========================
@app.route("/student_login", methods=["GET", "POST"])
def student_login():
    msg = ""
    if request.method == "POST":
        roll = request.form["roll"]
        pwd = request.form["password"]
        new_pwd = request.form.get("new_password")

        con = db()
        student = con.execute(
            "SELECT * FROM students WHERE roll=?",
            (roll,)
        ).fetchone()

        if not student:
            msg = "❌ Roll number not found"
        elif new_pwd:
            # Change password
            con.execute(
                "UPDATE students SET password=? WHERE roll=?",
                (new_pwd, roll)
            )
            con.commit()
            msg = "✅ Password updated successfully"
        elif student["password"] != pwd:
            msg = "❌ Incorrect password"
        else:
            session["student"] = roll
            con.close()
            return redirect("/student/dashboard")

        con.close()

    return render_template("student_login.html", msg=msg)

@app.route("/student/dashboard")
def student_dashboard():
    if "student" not in session:
        return redirect("/student_login")

    roll = session["student"]
    con = db()

    student = con.execute(
        "SELECT * FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    # Active exams only for this student
    active_exams = con.execute("""
        SELECT * FROM exams
        WHERE status='ACTIVE'
        AND year=? AND branch=? AND section=?
    """, (
        student["year"], student["branch"], student["section"]
    )).fetchall()

    # Previous papers (completed exams)
    papers = con.execute("""
        SELECT DISTINCT exam_id FROM exam_papers
        WHERE year=? AND branch=? AND section=?
    """, (
        student["year"], student["branch"], student["section"]
    )).fetchall()

    con.close()

    return render_template(
        "student_dashboard.html",
        student=student,
        active_exams=active_exams,
        papers=papers
    )


@app.route("/student/change_password", methods=["GET", "POST"])
def student_change_password():
    if request.method == "POST":
        roll = request.form["roll"]
        old_pass = request.form["old_password"]
        new_pass = request.form["new_password"]

        con = db()
        student = con.execute(
            "SELECT password FROM students WHERE roll=?",
            (roll,)
        ).fetchone()

        if not student or student["password"] != old_pass:
            con.close()
            return render_template(
                "change_password.html",
                error="❌ Old password is incorrect"
            )

        con.execute(
            "UPDATE students SET password=? WHERE roll=?",
            (new_pass, roll)
        )

        con.commit()
        con.close()

        return redirect("/student_login")

    return render_template("change_password.html")

@app.route("/student/exam/<int:exam_id>", methods=["GET", "POST"])
def student_exam(exam_id):

    if "student" not in session:
        return redirect("/student_login")

    roll = session["student"]
    con = db()

    try:
        # =========================
        # FETCH STUDENT
        # =========================
        student = con.execute(
            "SELECT * FROM students WHERE roll=?",
            (roll,)
        ).fetchone()

        if not student:
            return "❌ Student not found"

        # =========================
        # FETCH ACTIVE EXAM
        # =========================
        exam = con.execute(
            "SELECT * FROM exams WHERE id=? AND status='ACTIVE'",
            (exam_id,)
        ).fetchone()

        if not exam:
            return "❌ Exam not active"

        # =========================
        # ELIGIBILITY CHECK
        # =========================
        if (student["year"], student["branch"], student["section"]) != \
           (exam["year"], exam["branch"], exam["section"]):
            return "❌ You are not eligible for this exam"

        # =========================
        # PREVENT DOUBLE SUBMISSION
        # =========================
        already = con.execute(
            "SELECT 1 FROM results WHERE roll=? AND exam_id=?",
            (roll, exam_id)
        ).fetchone()

        if already:
            return redirect("/student/dashboard")

        # =========================
        # SUBMIT EXAM
        # =========================
        if request.method == "POST":

            questions = con.execute(
                "SELECT * FROM questions WHERE exam_id=?",
                (exam_id,)
            ).fetchall()

            score = 0
            for q in questions:
                ans = request.form.get(str(q["id"]))
                if not ans:
                    continue

                correct = q["correct"]
                if not correct:
                    continue

                if correct.strip().lower() in ["a", "b", "c", "d"]:
                    if ans.strip().lower() == correct.strip().lower():
                        score += 1
                else:
                    selected = {
                        "a": q["a"],
                        "b": q["b"],
                        "c": q["c"],
                        "d": q["d"]
                    }.get(ans.strip().lower())

                    if selected and selected.strip().lower() == correct.strip().lower():
                        score += 1

            # =========================
            # SAVE RESULT
            # =========================
            con.execute(
                "INSERT OR IGNORE INTO results "
                "(roll, exam_id, marks, submit_time) "
                "VALUES (?,?,?,DATETIME('now'))",
                (roll, exam_id, score)
            )

            # =========================
            # SAVE ATTENDANCE
            # =========================
            con.execute(
                "INSERT OR IGNORE INTO attendance "
                "(exam_id, roll, status, attended_on) "
                "VALUES (?,?,?,DATE('now'))",
                (exam_id, roll, "PRESENT")
            )

            # =========================
            # SAVE EXAM PAPER
            # =========================
            exists = con.execute(
                "SELECT 1 FROM exam_papers WHERE exam_id=?",
                (exam_id,)
            ).fetchone()

            if not exists:
                for q in questions:
                    con.execute("""
                        INSERT INTO exam_papers
                        (exam_id, year, branch, section, exam_date,
                         question, a, b, c, d, correct)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        exam_id,
                        exam["year"],
                        exam["branch"],
                        exam["section"],
                        exam["exam_date"],
                        q["question"],
                        q["a"],
                        q["b"],
                        q["c"],
                        q["d"],
                        q["correct"]
                    ))

            con.commit()

            # =========================
            # SEND SMS TO PARENT (EN + TE)
            # =========================
                        # =========================
            # SEND SMS TO PARENT (SAFE FIX)
            # =========================
            parent_number = student["parent"]

            # Auto add +91 if missing
            if parent_number and not parent_number.startswith("+"):
                parent_number = "+91" + parent_number

            send_sms(
                parent_number,
                f"""
KIET Exam Result

Student: {student['name']}
Roll: {student['roll']}
Marks: {score}

Year: {student['year']}
Branch: {student['branch']}
Section: {student['section']}
"""
            )

            return render_template(
                "student_result.html",
                score=score
            )

        # =========================
        # LOAD QUESTIONS (GET)
        # =========================
        questions = con.execute(
            "SELECT id, question, a, b, c, d FROM questions WHERE exam_id=?",
            (exam_id,)
        ).fetchall()

        return render_template(
            "student_exam.html",
            questions=questions,
            duration=exam["duration"]
        )

    finally:
        con.close()

@app.route("/student/papers", methods=["GET"])
def student_papers():

    if "student" not in session:
        return redirect("/student_login")

    roll = session["student"]
    con = db()

    # Fetch student info
    student = con.execute(
        "SELECT * FROM students WHERE roll=?",
        (roll,)
    ).fetchone()

    # Filters
    year = request.args.get("year", student["year"])
    branch = request.args.get("branch", student["branch"])
    section = request.args.get("section", student["section"])
    date = request.args.get("date")

    query = """
        SELECT DISTINCT
            exam_id,
            year,
            branch,
            section,
            exam_date
        FROM exam_papers
        WHERE year=? AND branch=? AND section=?
    """

    params = [year, branch, section]

    if date:
        query += " AND exam_date=?"
        params.append(date)

    query += " ORDER BY exam_date DESC"

    papers = con.execute(query, params).fetchall()
    con.close()

    return render_template(
        "student_papers.html",
        papers=papers,
        student=student
    )

@app.route("/student/paper/<int:exam_id>")
def download_paper(exam_id):

    if "student" not in session:
        return redirect("/student_login")

    con = db()
    qs = con.execute(
        "SELECT * FROM exam_papers WHERE exam_id=?",
        (exam_id,)
    ).fetchall()
    con.close()

    if not qs:
        return "❌ Question paper not available"

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    y = 800

    for q in qs:
        pdf.drawString(40, y, q["question"] or "")
        y -= 20

        pdf.drawString(60, y, "A) " + (q["a"] or ""))
        y -= 15

        pdf.drawString(60, y, "B) " + (q["b"] or ""))
        y -= 15

        pdf.drawString(60, y, "C) " + (q["c"] or ""))
        y -= 15

        pdf.drawString(60, y, "D) " + (q["d"] or ""))
        y -= 15

        pdf.drawString(60, y, "Answer: " + (q["correct"] or ""))
        y -= 30

        # New page if space ends
        if y < 100:
            pdf.showPage()
            y = 800

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"exam_{exam_id}_paper.pdf",
        mimetype="application/pdf"
    )

# =========================
# LOGOUT
# =========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =========================
# RUN (CRITICAL FIX)
# =========================
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
