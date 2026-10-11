"""Migration and backfill script for dual currency (EUR/JOD) and exact disbursement dates."""
import os
import sys
import sqlite3

# Ensure backend directory is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, engine
from app.models import DisbursementBatch, DisbursementItem


def migrate_fx_columns():
    """Add columns to SQLite tables if they do not exist."""
    db_path = os.path.join(backend_dir, "finnspark.db")
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check disbursement_batches columns
    cursor.execute("PRAGMA table_info(disbursement_batches)")
    b_cols = [row[1] for row in cursor.fetchall()]
    print("disbursement_batches columns:", b_cols)

    if "disbursement_currency" not in b_cols:
        print("Adding column disbursement_currency to disbursement_batches...")
        cursor.execute("ALTER TABLE disbursement_batches ADD COLUMN disbursement_currency VARCHAR(10) DEFAULT 'JOD'")

    if "exchange_rate" not in b_cols:
        print("Adding column exchange_rate to disbursement_batches...")
        cursor.execute("ALTER TABLE disbursement_batches ADD COLUMN exchange_rate FLOAT DEFAULT 0.76")

    if "total_amount_jod" not in b_cols:
        print("Adding column total_amount_jod to disbursement_batches...")
        cursor.execute("ALTER TABLE disbursement_batches ADD COLUMN total_amount_jod FLOAT DEFAULT 0.0")

    # Check disbursement_items columns
    cursor.execute("PRAGMA table_info(disbursement_items)")
    i_cols = [row[1] for row in cursor.fetchall()]
    print("disbursement_items columns:", i_cols)

    if "amount_jod" not in i_cols:
        print("Adding column amount_jod to disbursement_items...")
        cursor.execute("ALTER TABLE disbursement_items ADD COLUMN amount_jod FLOAT DEFAULT 0.0")

    if "disbursement_date" not in i_cols:
        print("Adding column disbursement_date to disbursement_items...")
        cursor.execute("ALTER TABLE disbursement_items ADD COLUMN disbursement_date DATE")

    if "exchange_rate" not in i_cols:
        print("Adding column exchange_rate to disbursement_items...")
        cursor.execute("ALTER TABLE disbursement_items ADD COLUMN exchange_rate FLOAT")

    conn.commit()
    conn.close()
    print("Schema migration completed successfully.")


def backfill_disbursements_data():
    """Backfill existing disbursement batches and items with exchange rates and exact dates."""
    db = SessionLocal()
    try:
        batches = db.query(DisbursementBatch).all()
        print(f"Found {len(batches)} batches to backfill.")

        for b in batches:
            if not b.currency:
                b.currency = "EUR"
            b.disbursement_currency = "JOD"
            if not b.exchange_rate:
                b.exchange_rate = 0.76
            rate = b.exchange_rate

            b_total_jod = 0.0
            for item in b.items:
                if not item.disbursement_date:
                    item.disbursement_date = b.payment_date
                if not item.exchange_rate:
                    item.exchange_rate = rate
                amt = float(item.amount or 0.0)
                it_jod = round(amt * (item.exchange_rate or rate), 3)
                item.amount_jod = it_jod
                if item.is_included:
                    b_total_jod += it_jod

            b.total_amount_jod = round(b_total_jod, 3)

        db.commit()
        print("Successfully backfilled all batches and items with FX and exact dates.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate_fx_columns()
    backfill_disbursements_data()
