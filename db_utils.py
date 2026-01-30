# db_utils.py
# Authentication + Project configuration + Execution results (FINAL, STABLE)

import mysql.connector
from mysql.connector import Error
import logging
import bcrypt
from config import DB_CONFIG
from logs import logger

logging.basicConfig(level=logging.INFO)

logger.info("db_utils module loaded")
# =====================================================
# DB CONNECTION
# =====================================================
def connect_db():
    logger.info("connect_db called")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        logger.info("Database connection established")
        return conn
    except Error as e:
        logging.error(e)
        logger.error(f"Database connection failed: {e}")
        return None


# =====================================================
# AUTHENTICATION
# =====================================================
def authenticate_user(username: str, password: str, role: str):
    logger.info(
        f"authenticate_user called | username={username}, role={role}"
    )
    conn = connect_db()
    if not conn:
        logger.error("Authentication failed: DB connection failed")  
        return False, "Database connection failed"

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM users WHERE username=%s AND role=%s",
            (username, role)
        )
        user = cur.fetchone()

        if not user:
            logger.warning(f"Authentication failed: invalid user {username}")  
            return False, "Invalid username or role"

        stored = user["password_hash"]

        # Plain text (temporary)
        if stored == password:
            logging.info(f"Login success (plain) for {username}")
            logger.info(f"Login success (plain) for {username}")  
            return True, role

        # bcrypt
        if stored.startswith("$2"):
            if bcrypt.checkpw(password.encode(), stored.encode()):
                logging.info(f"Login success (bcrypt) for {username}")
                logger.info(f"Login success (bcrypt) for {username}")  
                return True, role

        logger.warning(f"Authentication failed: invalid password for {username}")  
        return False, "Invalid password"

    except Error as e:
        logging.error(e)
        logger.error(f"Authentication DB error: {e}")  
        return False, "Database error"

    finally:
        cur.close()
        conn.close()
        logger.info("Authentication DB connection closed")  

    # =====================================================
    # TABLE CREATION (FIXED + VERBOSE)
    # =====================================================


# =====================================================
# TABLE CREATION (SAFE + MYSQL-CONNECTOR FIX)
# =====================================================
def create_tables():
    print("[DB] create_tables() called")
    logger.info("create_tables called")  

    conn = connect_db()
    if not conn:
        print("[DB][ERROR] Database connection failed")
        logger.error("create_tables failed: DB connection failed")  
        return

    print("[DB] Connected to database:", DB_CONFIG.get("database"))
    logger.info(f"Connected to database: {DB_CONFIG.get('database')}")  

    cur = conn.cursor()
    try:
        print("[DB] Ensuring table: projects")
        logger.info("Ensuring table: projects")  

        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_name VARCHAR(255) NOT NULL,
                    sn INT NOT NULL,
                    description TEXT,
                    r VARCHAR(50),
                    y VARCHAR(50),
                    b VARCHAR(50),
                    n VARCHAR(50),
                    expected_v VARCHAR(50),
                    expected_i VARCHAR(50),
                    enabled BOOLEAN,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (project_name, sn)
                )
            """)
        except mysql.connector.Error as e:
            if e.errno != 1050:
                raise
            print("[DB] projects table already exists")
            logger.info("projects table already exists")  

        print("[DB] Ensuring table: test_results")
        logger.info("Ensuring table: test_results")  

        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS test_results (
                    project_name VARCHAR(255) NOT NULL,
                    pcb_serial VARCHAR(255) NOT NULL,
                    sn INT NOT NULL,
                    description TEXT,
                    r VARCHAR(50),
                    y VARCHAR(50),
                    b VARCHAR(50),
                    n VARCHAR(50),
                    expected_v VARCHAR(50),
                    expected_i VARCHAR(50),
                    measured_v VARCHAR(50),
                    measured_i VARCHAR(50),
                    result VARCHAR(50),
                    tested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (project_name, pcb_serial, sn)
                )
            """)
        except mysql.connector.Error as e:
            if e.errno != 1050:
                raise
            print("[DB] test_results table already exists")
            logger.info("test_results table already exists")  

        conn.commit()
        print("[DB] Database schema ready")
        logger.info("Database schema ready")  

    except Exception as e:
        print("[DB][FATAL] Schema creation failed")
        print(e)
        logger.error(f"Schema creation failed: {e}")  

    finally:
        cur.close()
        conn.close()
        print("[DB] Database connection closed")
        logger.info("Database connection closed after create_tables")  


# =====================================================
# SAVE PROJECT CONFIG (FULL OVERWRITE)
# =====================================================
def save_project(project_name: str, test_cases: list):
    logger.info(f"save_project called | project={project_name}")  

    conn = connect_db()
    if not conn:
        logger.error("save_project failed: DB connection failed")  
        return

    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM projects WHERE project_name=%s",
            (project_name,)
        )

        for sn, tc in enumerate(test_cases, start=1):
            cur.execute("""
                INSERT INTO projects
                (project_name, sn, description, r, y, b, n,
                 expected_v, expected_i, enabled)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                project_name,
                sn,
                tc["desc"],
                tc["r"], tc["y"], tc["b"], tc["n"],
                tc["v"], tc["i"],
                bool(tc["enabled"])
            ))

        conn.commit()
        logging.info(f"Project '{project_name}' saved")
        logger.info(f"Project '{project_name}' saved successfully")  

    finally:
        cur.close()
        conn.close()
        logger.info("DB connection closed after save_project")  


# =====================================================
# LOAD PROJECT LIST
# =====================================================
def load_projects():
    logger.info("load_projects called")  

    conn = connect_db()
    if not conn:
        logger.error("load_projects failed: DB connection failed")  
        return []

    cur = conn.cursor()
    cur.execute("""
        SELECT project_name
        FROM projects
        GROUP BY project_name
        ORDER BY MAX(saved_at) DESC
    """)
    names = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    logger.info(f"load_projects returned {len(names)} projects")  
    return names


# =====================================================
# LOAD PROJECT CONFIG (ALL ROWS)
# =====================================================
def load_project_rows(project_name: str):
    logger.info(f"load_project_rows called | project={project_name}")  

    conn = connect_db()
    if not conn:
        logger.error("load_project_rows failed: DB connection failed")  
        return []

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT sn, description, r, y, b, n,
               expected_v, expected_i, enabled
        FROM projects
        WHERE project_name=%s
        ORDER BY sn
    """, (project_name,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    logger.info(f"Loaded {len(rows)} rows for project '{project_name}'")  

    return [{
        "sn": r["sn"],
        "desc": r["description"],
        "r": r["r"],
        "y": r["y"],
        "b": r["b"],
        "n": r["n"],
        "v": r["expected_v"],
        "i": r["expected_i"],
        "enabled": bool(r["enabled"])
    } for r in rows]


# =====================================================
# LOAD ENABLED TEST CASES (EXECUTION)
# =====================================================
def load_test_cases(project_name: str):
    logger.info(f"load_test_cases called | project={project_name}")  

    conn = connect_db()
    if not conn:
        logger.error("load_test_cases failed: DB connection failed")  

        return []

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT sn, description, r, y, b, n,
               expected_v, expected_i
        FROM projects
        WHERE project_name=%s AND enabled=TRUE
        ORDER BY sn
    """, (project_name,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    logger.info(f"Enabled test cases loaded: {len(rows)}")  

    return [{
        "sn": r["sn"],
        "desc": r["description"],
        "r": r["r"],
        "y": r["y"],
        "b": r["b"],
        "n": r["n"],
        "v": r["expected_v"],
        "i": r["expected_i"]
    } for r in rows]


# =====================================================
# SAVE / UPDATE TEST RESULT (MYSQL 8 SAFE)
# =====================================================
def save_test_result(project_name, pcb_serial, sn, data):
    logger.info(f"save_test_result called | Project={project_name}, PCB={pcb_serial}, SN={sn}")

    conn = connect_db()
    if not conn:
        print("[DB][ERROR] save_test_result: DB connection failed")
        return

    cur = conn.cursor()
    try:
        print(f"[DB] Saving test result → Project={project_name}, PCB={pcb_serial}, SN={sn}")
        logger.error("save_test_result failed: DB connection failed")  

        cur.execute("""
            INSERT INTO test_results
            (
                project_name, pcb_serial, sn, description,
                r, y, b, n,
                expected_v, expected_i,
                measured_v, measured_i, result
            )
            VALUES
            (
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,
                %s,%s,%s
            ) AS new
            ON DUPLICATE KEY UPDATE
                measured_v = new.measured_v,
                measured_i = new.measured_i,
                result     = new.result,
                tested_at  = CURRENT_TIMESTAMP
        """, (
            project_name,
            pcb_serial,
            sn,
            data["desc"],
            data["r"],
            data["y"],
            data["b"],
            data["n"],
            data["v"],
            data["i"],
            data["measured_v"],
            data["measured_i"],
            data["result"]
        ))

        conn.commit()
        print("[DB] Test result saved successfully")
        logger.info("Test result saved successfully")  

    except Exception as e:
        print("[DB][FATAL] Failed to save test result")
        print(e)
        logger.error(f"Failed to save test result: {e}")  
        raise   # IMPORTANT: propagate real DB failure

    finally:
        cur.close()
        conn.close()
        logger.info("DB connection closed after save_test_result")  

def delete_project(project_name: str):
    """
    Delete a project and all its test cases from database
    """
    logger.info(f"delete_project called | project={project_name}")  

    conn =  connect_db()
    cursor = conn.cursor()

    try:
        logger.info(f"Deleting project records for '{project_name}'")  

        # If you have a separate project table
        cursor.execute(
            "DELETE FROM projects WHERE project_name=%s",
            (project_name,)
        )

        logger.info(f"Deleted from projects table | project={project_name}")  

        # If test cases are stored separately
        #cursor.execute(
            #"DELETE FROM project_test_cases WHERE project_name = %s",
            #(project_name,)
        #)

       # logger.info(f"Deleted from project_test_cases table | project={project_name}")

        conn.commit()
        logger.info(f"Project '{project_name}' deleted successfully")  

    except Exception as e:
        conn.rollback()
        logger.error(f"delete_project failed | project={project_name} | error={e}" )
        raise e

    finally:
        cursor.close()
        conn.close()
        logger.info(f"DB connection closed after delete_project | project={project_name}")

