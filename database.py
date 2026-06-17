import sqlite3
import csv
from io import StringIO, BytesIO
from datetime import datetime
import re
import pandas as pd

DB_NAME = 'investments.db'

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for sep in ['.', '-', ' ']:
        date_str = date_str.replace(sep, '/')
    parts = date_str.split('/')
    if len(parts) != 3:
        return None
    day, month, year = parts
    if len(year) == 2:
        year = '20' + year if int(year) < 30 else '19' + year
    try:
        dt = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", '%Y-%m-%d')
        return dt.strftime('%Y-%m-%d')
    except:
        return None

def parse_number(s):
    if not s:
        return 0.0
    s = s.replace(' ', '').replace(',', '.').strip()
    try:
        return float(s)
    except:
        return 0.0

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn

def create_tables(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            comment TEXT,
            type TEXT DEFAULT 'Доля',
            share_percent REAL,
            investment_amount REAL,
            contract_number TEXT
        )
    ''')
    for col in ['share_percent', 'investment_amount', 'contract_number']:
        try:
            cursor.execute(f'ALTER TABLE projects ADD COLUMN {col} TEXT')
        except sqlite3.OperationalError:
            pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            project_id INTEGER,
            amount REAL NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            category TEXT,
            comment TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT,
            comment TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            investment REAL,
            method TEXT,
            mode TEXT,
            term_months INTEGER,
            total_return REAL,
            profit REAL,
            rate REAL,
            dividends REAL,
            exit_price REAL,
            roi REAL,
            annual_return REAL,
            deposit_rate REAL,
            discount_rate REAL,
            npv REAL,
            irr REAL
        )
    ''')
    conn.commit()

def get_projects():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, comment, type, share_percent, investment_amount, contract_number FROM projects ORDER BY name')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_project(name, comment='', type_='Доля', share_percent=None, investment_amount=None, contract_number=''):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (name, comment, type, share_percent, investment_amount, contract_number)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, comment, type_, share_percent, investment_amount, contract_number))
    conn.commit()
    conn.close()

def delete_project(project_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()

def add_operation(date, project_id, amount, type_, category, comment):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO operations (date, project_id, amount, type, category, comment)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, project_id, amount, type_, category, comment))
    conn.commit()
    conn.close()

def get_operations(limit=None, project_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = '''
        SELECT o.id, o.date, p.name as project_name, o.amount, o.type, o.category, o.comment
        FROM operations o
        LEFT JOIN projects p ON o.project_id = p.id
    '''
    params = []
    if project_id:
        query += ' WHERE o.project_id = ?'
        params.append(project_id)
    query += ' ORDER BY o.date DESC'
    if limit:
        query += ' LIMIT ?'
        params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_operation(op_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM operations WHERE id = ?', (op_id,))
    conn.commit()
    conn.close()

def get_project_aggregates():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            p.id,
            p.name,
            p.type,
            p.share_percent,
            p.investment_amount,
            p.contract_number,
            COALESCE(SUM(CASE WHEN o.type = 'income' THEN o.amount ELSE 0 END), 0) as total_in,
            COALESCE(SUM(CASE WHEN o.type = 'expense' THEN o.amount ELSE 0 END), 0) as total_out
        FROM projects p
        LEFT JOIN operations o ON p.id = o.project_id
        GROUP BY p.id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_history(data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history (
            date, investment, method, mode, term_months, total_return, profit,
            rate, dividends, exit_price, roi, annual_return,
            deposit_rate, discount_rate, npv, irr
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data['date'], data['investment'], data['method'], data['mode'],
        data['term_months'], data['total_return'], data.get('profit'),
        data.get('rate'), data.get('dividends'), data.get('exit_price'),
        data['roi'], data['annual_return'],
        data['deposit_rate'], data.get('discount_rate'),
        data.get('npv'), data.get('irr')
    ))
    conn.commit()
    conn.close()

def get_history(limit=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = 'SELECT * FROM history ORDER BY date DESC'
    if limit:
        query += f' LIMIT {limit}'
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_history_record(record_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM history WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def export_history_to_excel():
    records = get_history()
    df = pd.DataFrame(records)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='History')
    output.seek(0)
    return output.getvalue()

def export_operations_to_excel():
    ops = get_operations()
    df = pd.DataFrame(ops)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Operations')
    output.seek(0)
    return output.getvalue()

def get_payments():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.date, p.amount, p.type, p.comment, pr.name as project_name
        FROM payments p
        LEFT JOIN projects pr ON p.project_id = pr.id
        ORDER BY p.date
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_payments_from_excel(project_id, rows):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT type FROM projects WHERE id = ?', (project_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return
    project_type = row[0] if row[0] else 'Доля'
    for date_str, amount in rows:
        date_parsed = parse_date(date_str)
        if not date_parsed:
            continue
        if amount == 0:
            continue
        cursor.execute('''
            INSERT INTO payments (project_id, date, amount, type)
            VALUES (?, ?, ?, ?)
        ''', (project_id, date_parsed, amount, project_type))
    conn.commit()
    conn.close()
