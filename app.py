from flask import Flask, render_template, request
from openai import OpenAI
from dotenv import load_dotenv
import sqlite3
import os

load_dotenv()

app = Flask(__name__)

# -----------------------------
# GROQ CLIENT
# -----------------------------
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)


# -----------------------------
# DYNAMIC SCHEMA RETRIEVAL
# -----------------------------
def get_schema():

    conn = sqlite3.connect("company.db")

    cursor = conn.cursor()

    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type='table'
    """)

    tables = cursor.fetchall()

    schema = ""

    for table in tables:

        table_name = table[0]

        cursor.execute(f"PRAGMA table_info({table_name})")

        columns = cursor.fetchall()

        column_names = []

        for col in columns:
            column_names.append(col[1])

        schema += f"\n{table_name}(\n"

        schema += ",\n".join(column_names)

        schema += "\n)\n"

    conn.close()

    return schema


# -----------------------------
# CHECK TABLE EXISTS
# -----------------------------
def table_exists(table_name):

    conn = sqlite3.connect("company.db")

    cursor = conn.cursor()

    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type='table' AND name=?
    """, (table_name,))

    table = cursor.fetchone()

    conn.close()

    return table is not None


# -----------------------------
# CONVERT VALUES TO UPPERCASE
# -----------------------------
def convert_insert_values_to_upper(sql_query):

    query_type = sql_query.strip().split()[0].upper()

    if query_type not in ["INSERT", "UPDATE"]:
        return sql_query

    result = ""

    inside_quotes = False

    for char in sql_query:

        if char == "'":

            inside_quotes = not inside_quotes

            result += char

        elif inside_quotes:

            result += char.upper()

        else:

            result += char

    return result


# -----------------------------
# GENERATE HUMAN RESPONSE
# -----------------------------
def generate_human_response(question, results):

    prompt = f"""
You are a helpful AI database assistant.

User Question:
{question}

Database Results:
{results}

Generate a short human-friendly response.

Examples:
- "We found 2 students living in Hyderabad."
- "No matching records were found."
- "The employee details were updated successfully."

Keep response short and professional.
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# AI SQL GENERATOR
# -----------------------------
def generate_sql(question):

    schema = get_schema()

    prompt = f"""
You are an expert SQLite database assistant.

Convert the user's request into VALID SQLite SQL ONLY.

Database Schema:

{schema}

IMPORTANT SQLITE RULES:
- Use ONLY SQLite syntax.
- SQLite DOES NOT support:
  DESCRIBE
  SHOW TABLES
  SHOW DATABASES
- To inspect schema use:
  PRAGMA table_info(table_name)
- Return ONLY SQL queries.
- No explanations.
- Use correct table names.
- Multiple SQL statements are allowed if needed.
- If user asks to show a table,
  return SELECT * FROM table_name
- Use SQL aliases when user wording differs from column names.
- Example:
  address AS city
VERY IMPORTANT RULES:

- Return ONLY executable SQLITE SQL.
- No explanations.
- No markdown.
- No comments.

----------------------------------------
SCHEMA UNDERSTANDING
----------------------------------------

- Use ONLY tables and columns
  that EXIST in schema.

- NEVER invent columns.

- NEVER invent tables.

- Before generating SQL,
  carefully analyze schema.

- If a requested field does not exist,
  use related tables using JOIN.

----------------------------------------
RELATIONSHIP RULES
----------------------------------------

- Use JOIN queries whenever
  tables are related.

- Infer relationships from
  foreign keys and matching IDs.

Example:

PRODUCTS(id, name, price)

ORDERS(
    id,
    product_id,
    status,
    delivery_date
)

If user asks:

"pending products"

Generate:

SELECT PRODUCTS.*
FROM PRODUCTS
JOIN ORDERS
ON PRODUCTS.id = ORDERS.product_id
WHERE UPPER(ORDERS.status)='PENDING'

----------------------------------------
CASE INSENSITIVE SEARCH
----------------------------------------

- ALL text comparisons
  must use UPPER()

Example:

WHERE UPPER(name)='LAPTOP'

----------------------------------------
INSERT RULES
----------------------------------------

- ALL inserted text values
  must be uppercase.

----------------------------------------
SQLITE RULES
----------------------------------------

- SQLITE DOES NOT SUPPORT:
  DESCRIBE
  SHOW TABLES
  SHOW DATABASES
  ALTER TABLE ADD CONSTRAINT

- FOREIGN KEY constraints
  must be declared inside
  CREATE TABLE.

----------------------------------------
TABLE DISPLAY RULES
----------------------------------------

- If user asks:
  "show products"

Generate:
SELECT * FROM products

----------------------------------------
IMPORTANT
----------------------------------------

- NEVER generate unsupported syntax.
- NEVER hallucinate columns.
- NEVER generate extra unnecessary queries.
- Use exact schema names only.
- Ignore sqlite internal tables.
User Request:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# HOME ROUTE
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def home():

    results = []
    columns = []
    sql_query = ""
    error = ""
    question = ""
    ai_response = ""

    if request.method == "POST":
        

        question = request.form["question"]

        sql_query = generate_sql(question)

        # Remove markdown formatting
        sql_query = sql_query.replace("```sql", "")
        sql_query = sql_query.replace("```", "")
        sql_query = sql_query.strip()

        # Convert INSERT/UPDATE values to uppercase
        sql_query = convert_insert_values_to_upper(sql_query)

        try:

            conn = sqlite3.connect("company.db")

            cursor = conn.cursor()

            query_type = sql_query.strip().split()[0].upper()

            # -----------------------------
            # HANDLE TABLE ALREADY EXISTS
            # -----------------------------
            if query_type == "CREATE":

                words = sql_query.split()

                if "TABLE" in words:

                    table_index = words.index("TABLE") + 1

                    table_name = words[table_index]

                    table_name = table_name.replace("(", "")

                    if table_exists(table_name):

                        results = [("Table already exists",)]

                        ai_response = "The table already exists."

                        conn.close()

                        return render_template(
                            "index.html",
                            results=results,
                            columns=columns,
                            sql_query=sql_query,
                            error=error,
                            question=question,
                            ai_response=ai_response
                        )

            # -----------------------------
            # MULTIPLE SQL STATEMENTS
            # -----------------------------
            if ";" in sql_query.strip()[:-1]:

                cursor.executescript(sql_query)

                conn.commit()

                results = [("Multiple Operations Successful",)]

                ai_response = "Multiple database operations completed successfully."

            else:

                cursor.execute(sql_query)

                if query_type == "SELECT":

                    results = cursor.fetchall()

                    columns = [
                        description[0]
                        for description in cursor.description
                    ]

                    if len(results) == 0:

                        results = [("No records found",)]

                        columns = ["Message"]

                        ai_response = "No matching records were found."

                    else:

                        ai_response = generate_human_response(
                            question,
                            results
                        )

                else:

                    conn.commit()

                    results = [("Operation Successful",)]

                    ai_response = generate_human_response(
                        question,
                        results
                    )

            conn.close()

        except Exception as e:

            error = str(e)

    return render_template(
        "index.html",
        results=results,
        columns=columns,
        sql_query=sql_query,
        error=error,
        question=question,
        ai_response=ai_response
    )


# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)

