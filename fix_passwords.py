import sqlite3

con = sqlite3.connect("database.db")
cur = con.cursor()

cur.execute("""
UPDATE students
SET password='1234'
WHERE password IS NULL OR password=''
""")

con.commit()
con.close()

print("✅ Student passwords fixed")
