"""교육용 복식부기 총계정원장 생성: python3 run_gl.py"""
from __future__ import annotations
import csv
import sqlite3
from pathlib import Path
from src.audit_core import load_raw
from src.gl_core import ACCOUNTS, build_journals, flattened_gl, check_journal_balance, trial_balance, ar_by_invoice

ROOT = Path(__file__).resolve().parent
DERIVED = ROOT / "data" / "derived"
REPORTS = ROOT / "reports"

def export_csv(filename, rows):
    if not rows: return
    with filename.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main():
    raw = load_raw(ROOT / "data" / "raw")
    headers, lines = build_journals(raw)
    gl = flattened_gl(headers, lines)
    controls = check_journal_balance(headers, lines)
    tb = trial_balance(gl, 2025)
    ar = ar_by_invoice(gl)
    DERIVED.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    export_csv(DERIVED / "journal_headers.csv", headers)
    export_csv(DERIVED / "journal_lines.csv", lines)
    export_csv(DERIVED / "general_ledger.csv", gl)
    export_csv(DERIVED / "chart_of_accounts.csv", ACCOUNTS)
    export_csv(REPORTS / "journal_balance_checks.csv", controls)
    export_csv(REPORTS / "trial_balance_2025.csv", tb)
    export_csv(REPORTS / "ar_by_invoice.csv", ar)
    dbpath = REPORTS / "general_ledger.db"
    with sqlite3.connect(dbpath) as con:
        for name, rows in [("journal_headers", headers), ("journal_lines", lines),
                           ("general_ledger", gl), ("chart_of_accounts", ACCOUNTS)]:
            # 샘플 숫자 칼럼은 SQL SUM을 위해 INTEGER 타입 부여
            cols = list(rows[0])
            types = []
            for col in cols:
                ty = "INTEGER" if col in ("line_no", "fiscal_year", "debit_krw", "credit_krw") else "TEXT"
                types.append(f'"{col}" {ty}')
            con.execute(f'DROP TABLE IF EXISTS "{name}"')
            con.execute(f'CREATE TABLE "{name}" ({", ".join(types)})')
            con.executemany(f'INSERT INTO "{name}" VALUES ({",".join("?" for _ in cols)})',
                            [[r[c] for c in cols] for r in rows])
    print(f"GL 생성 완료: {len(headers)}개 전표, {len(lines)}개 차대변 라인")
    print(f"차대변 일치: {sum(x['check']=='정상' for x in controls)}/{len(controls)} 전표")
    print("2025년 시산표:", [(r["account_name"], r["net_debit_krw"], r["net_credit_krw"]) for r in tb])
    print("주의: 차대변이 일치해도 거래의 발생·기간귀속·정확성은 별도 감사절차가 필요")

if __name__ == '__main__':
    main()
