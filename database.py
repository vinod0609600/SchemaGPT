import sqlite3

conn = sqlite3.connect("company.db")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY,
    name TEXT,
    salary INTEGER,
    department TEXT
)
""")

cursor.execute("""
INSERT INTO employees (name, salary, department)
VALUES
('Vinod', 60000, 'AI'),
('Rahul', 45000, 'HR'),
('Anjali', 70000, 'Finance'),
('Kiran', 55000, 'AI')
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS info (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER,
    address TEXT,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
)
""")

cursor.execute("""
INSERT INTO info (employee_id, address)
VALUES
(1, 'HYD'),
(2, 'Bangalore'),
(3, 'Chennai')
""")

conn.commit()

conn.close()

print("Database Created Successfully")