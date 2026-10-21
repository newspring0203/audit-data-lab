"""실행: python3 run_audit.py"""
from __future__ import annotations
import csv
import sqlite3
from pathlib import Path
from src.audit_core import analyze_files, load_raw

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data/raw"
OUT = ROOT / "reports"

def save_csv(path, rows):
    if not rows: return
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)

def main():
    OUT.mkdir(exist_ok=True)
    register, exceptions = analyze_files(RAW)
    save_csv(OUT/"transaction_register.csv",register)
    save_csv(OUT/"review_exceptions.csv",exceptions)
    save_csv(OUT/"audit_workpaper_template.csv",exceptions)

    # SQL로 동일 데이터 분석 연습 가능하게 SQLite에도 저장
    db_path=OUT/"audit_lab.db"
    if db_path.exists(): db_path.unlink()
    con=sqlite3.connect(db_path)
    raw=load_raw(RAW)
    for dataset,records in raw.items():
        if not records: continue
        cols=list(records[0])
        defs=", ".join(f'"{c}" TEXT' for c in cols)
        con.execute(f'CREATE TABLE "{dataset}" ({defs})')
        placeholders=", ".join("?" for _ in cols)
        con.executemany(
            f'INSERT INTO "{dataset}" VALUES ({placeholders})',
            [[r[c] for c in cols] for r in records]
        )
    if exceptions:
        cols=list(exceptions[0])
        defs=", ".join(f'"{c}" TEXT' for c in cols)
        con.execute(f'CREATE TABLE "exceptions" ({defs})')
        con.executemany(
            'INSERT INTO "exceptions" VALUES ('+",".join("?" for _ in cols)+")",
            [[str(r[c]) for c in cols] for r in exceptions]
        )
    con.commit(); con.close()

    md=[
        "# 모의 매출 감사 데이터 검증 결과",
        "",
        "> 연습용 가상 데이터. 감사의견이 아니며 오류·부정을 확정하지 않습니다.",
        "",
        f"- 매출 ERP 행 수: {sum(x['erp_entry_count'] for x in register)}",
        f"- 청구서 기준 거래 수: {len(register)}",
        f"- 추가 검토 후보: {len(exceptions)}건",
        "",
        "| 청구서 | 검증 규칙 | 관찰한 사실 | 검토할 근거 |",
        "|---|---|---|---|",
    ]
    for e in exceptions:
        md.append(f"| {e['invoice_id']} | {e['rule_id']} | {e['observed_fact']} | {e['next_evidence']} |")
    md.extend(["","## 중요한 해석",
        "- 청구서/인도증빙에 없다고 해서 무조건 잘못된 매출은 아닙니다. 자료 추가 요청이 필요합니다.",
        "- 입금이 아직 없다는 사실만으로 매출이 틀렸다고 볼 수 없습니다.",
        "- 매출 완전성 검증은 **제공된 청구서·인도증빙 목록에 대해서만** 수행했습니다.",
        "- 실제 감사에는 자료 모집단의 완전성 검토, 통제, 회계기준 검토, 중요성 평가 등이 필요합니다.",
    ])
    (OUT/"summary.md").write_text("\n".join(md)+"\n",encoding="utf-8")

    from collections import Counter
    print(f"거래 {len(register)}건 / 검토 후보 {len(exceptions)}건")
    for row in exceptions:
        print(f"  {row['invoice_id']}: {row['rule_id']} ({row['audit_assertion']})")
    print("결과 폴더:", OUT)

if __name__ == "__main__":
    main()
