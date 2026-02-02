import sqlite3
import json
from datetime import datetime
import os

DB_PATH = "candidates.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            email TEXT,
            resume_score INTEGER,
            resume_analysis TEXT,
            extracted_topics TEXT,
            question_bank TEXT,
            interview_data TEXT,
            interview_score REAL,
            status TEXT,
            final_summary TEXT DEFAULT NULL,
            can_hire TEXT DEFAULT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migration Check
    try:
        c.execute("SELECT final_summary FROM candidates LIMIT 1")
    except sqlite3.OperationalError:
        print("Migrating DB: Adding final_summary column...")
        c.execute("ALTER TABLE candidates ADD COLUMN final_summary TEXT DEFAULT NULL")
        c.execute("ALTER TABLE candidates ADD COLUMN can_hire TEXT DEFAULT NULL")
    
    try:
        c.execute("SELECT question_bank FROM candidates LIMIT 1")
    except sqlite3.OperationalError:
        print("Migrating DB: Adding question_bank column...")
        c.execute("ALTER TABLE candidates ADD COLUMN question_bank TEXT DEFAULT NULL")

        
    conn.commit()
    conn.close()

def add_candidate(name: str, score: int, analysis: dict, topics: list, question_bank: list | None = None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if exists, update if so (or ignore)
        # For this logic, we'll INSERT OR REPLACE or just INSERT
        
        c.execute('''
            INSERT OR REPLACE INTO candidates (name, resume_score, resume_analysis, extracted_topics, question_bank, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name.lower(), score, json.dumps(analysis), json.dumps(topics), json.dumps(question_bank or []), 'screened'))
        
        conn.commit()
    except Exception as e:
        print(f"Error adding candidate: {e}")
    finally:
        conn.close()

def get_candidate(name: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM candidates WHERE name = ?", (name.lower(),))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_interview_result(name: str, evaluations: list, avg_score: float, final_summary: str = None, decision: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE candidates 
        SET interview_data = ?, interview_score = ?, status = ?, final_summary = ?, can_hire = ?
        WHERE name = ?
    ''', (json.dumps(evaluations), avg_score, 'completed', final_summary, decision, name.lower()))
    conn.commit()
    conn.close()

def update_recommendation(name: str, final_summary: str, decision: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE candidates
        SET final_summary = ?, can_hire = ?
        WHERE name = ?
    ''', (final_summary, decision, name.lower()))
    conn.commit()
    conn.close()

def get_all_candidates():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM candidates ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM candidates")
        conn.commit()
    except Exception as e:
        print(f"Error clearing DB: {e}")
    finally:
        conn.close()
