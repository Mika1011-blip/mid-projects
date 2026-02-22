from flask import Flask, request, jsonify
import sqlite3
import os
from pathlib import Path
from app.services.firebase_service import fetch_all_users

DB_PATH = Path(__file__).resolve().parent.parent.parent / 'RA_webapp.db'

def get_conn():
    db_existed = os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if not db_existed:
        # multiple statements in one go:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            uid         TEXT    UNIQUE NOT NULL,
            role        INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS patients (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uid           TEXT    NOT NULL,
            name          TEXT    NOT NULL,
            age           INTEGER NOT NULL,
            sex           TEXT    NOT NULL,
            telephone     TEXT    NOT NULL,
            email         TEXT    NOT NULL,
            retina_left   TEXT,
            retina_right  TEXT,
            diagnosis     TEXT,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(uid) REFERENCES users(uid)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_uid_name_tel
          ON patients(uid, name, telephone);
        """)
        '''
        users = fetch_all_users()
        if users:
            for user in users:
                print("inserting")
                conn.execute("INSERT INTO users (uid, role) VALUES (?, ?)", (user['uid'], 0))
        '''
        conn.commit()


    return conn

def search_user(uid):
    """
    Return a dict of the user record matching the given uid,
    or None if no such user exists.
    
    The returned dict will have these keys:
      id, uid, role, created_at
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    
    # Get column names and the first row (or None)
    cols = [col[0] for col in cur.description]
    row = cur.fetchone()
    conn.close()
    
    if row:
        user = dict(zip(cols, row))
        print(f"Found user: {user}")
        return user
    else:
        print(f"No user found with uid={uid!r}")
        return None
   

def add_user(uid):
    # If someone passed the whole JSON payload, pull out the string
    if isinstance(uid, dict):
        uid = uid.get('uid')

    if not isinstance(uid, str):
        raise ValueError(f"add_user: expected a string uid, got {type(uid).__name__}")

    conn = get_conn()
    cur  = conn.cursor()

    # skip existing
    if search_user(uid):
        print(f"[DEBUG] {uid!r} already exists → skipping insert")
        conn.close()
        return False

    cur.execute(
      "INSERT INTO users(uid, role) VALUES(?, ?)",
      (uid, 0)
    )
    print(f"[DEBUG] Inserted {uid!r}, rowcount = {cur.rowcount}")

    conn.commit()
    conn.close()
    return True


def update_user_role(uid: str, role: int):
    """
    Set the `role` (0 or 1) for the user with this uid.
    Returns True if a row was updated, False otherwise.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role = ? WHERE uid = ?", (role, uid))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return bool(changed)


def db_remove_user(uid):
    """
    Delete the user row with uid = uid.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE uid = ?", (uid,))
    if cur.rowcount:
        print(f"Deleted user uid={uid}.")
    else:
        print(f"No user found with uid={uid}; nothing deleted.")
    conn.commit()
    conn.close()


def add_patients(patients):
    """
    Accepts either a single dict or a list of dicts with keys:
      uid, name, age, sex, telephone, email
      [optional: retina_left, retina_right, diagnosis]
    Each `uid` (caretaker) may have multiple patients.
    """
    # 1) Normalize to a list
    if isinstance(patients, dict):
        patients = [patients]

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_uid_name_tel
      ON patients(uid, name, telephone)
    """)
    conn.commit()

    # 3) Insert or skip each patient
    for patient in patients:
        # validate required fields
        required = ['uid','name','age','sex','telephone','email']
        missing = [k for k in required if k not in patient]
        if missing:
            print(f"Skipping entry: missing required fields {missing}")
            continue

        # check for existing patient under same caretaker
        cur.execute(
            "SELECT 1 FROM patients WHERE uid = ? AND name = ? AND telephone = ?",
            (patient['uid'], patient['name'], patient['telephone'])
        )
        if cur.fetchone():
            print(f"Skipped {patient['name']} (uid={patient['uid']}): already exists")
            continue

        # build insertion columns & values
        cols = ['uid','name','age','sex','telephone','email']
        vals = [patient[k] for k in cols]
        for opt in ('retina_left','retina_right','diagnosis'):
            if opt in patient:
                cols.append(opt)
                vals.append(patient[opt])

        placeholders = ','.join('?' for _ in cols)
        col_list     = ','.join(cols)

        cur.execute(
            f"INSERT INTO patients ({col_list}) VALUES ({placeholders})",
            tuple(vals)
        )
        print(f"Inserted patient {patient['name']} (uid={patient['uid']})")

    conn.commit()
    conn.close()
    print("Adding patients completed")


def update_patient(patient_id, updates):
    """
    Update the patient with primary key `id = patient_id`.
    `updates` is a dict of column:value pairs to change.
    Only the keys present in `updates` will be modified; everything else is left untouched.

    Example:
      update_patient(
          42,
          {'age': 65, 'diagnosis': 'glaucoma'}
      )
    """
    if not updates:
        raise ValueError("No updates provided")

    # Only allow actual table columns:
    allowed = {
        'uid', 'name', 'age', 'sex', 'telephone', 'email',
        'retina_left', 'retina_right', 'diagnosis'
    }
    bad = set(updates) - allowed
    if bad:
        raise ValueError(f"Cannot update unknown columns: {bad}")

    # Build the SET clause and values list
    set_clauses = []
    vals = []
    for col, val in updates.items():
        set_clauses.append(f"{col} = ?")
        vals.append(val)

    set_sql = ", ".join(set_clauses)
    vals.append(patient_id)  # for the WHERE clause

    # Execute the UPDATE
    conn = get_conn()
    cur = conn.cursor()
    sql = f"UPDATE patients SET {set_sql} WHERE id = ?"
    cur.execute(sql, vals)

    if cur.rowcount:
        print(f"Updated patient id={patient_id}: {cur.rowcount} row(s) changed.")
    else:
        print(f"No patient found with id={patient_id}; nothing updated.")

    conn.commit()
    conn.close()



def remove_patient(patient_id):
    """
    Delete the patient row with primary key id = patient_id.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    if cur.rowcount:
        print(f"Deleted patient id={patient_id} ({cur.rowcount} row).")
    else:
        print(f"No patient found with id={patient_id}; nothing deleted.")
    conn.commit()
    conn.close()


def search_patients(email=None, telephone=None):
    """
    Return a list of patient records matching either email or telephone.
    You must supply exactly one of email or telephone.
    
    Returns:
        List[dict] where each dict has the full patient row:
          id, uid, name, age, sex, telephone, email,
          retina_left, retina_right, diagnosis, created_at
    """
    if bool(email) == bool(telephone):
        raise ValueError("Provide exactly one: email or telephone")

    conn = get_conn()
    cur = conn.cursor()

    if email:
        cur.execute("SELECT * FROM patients WHERE email = ?", (email,))
    else:
        cur.execute("SELECT * FROM patients WHERE telephone = ?", (telephone,))

    cols = [col[0] for col in cur.description]
    rows = cur.fetchall()
    conn.close()

    results = [dict(zip(cols, row)) for row in rows]
    if results:
        print(f"Found {len(results)} patient(s).")
    else:
        print("No matching patients found.")
    return results



