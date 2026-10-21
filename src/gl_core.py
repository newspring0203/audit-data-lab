"""간소화 ERP 매출 원본을 전표 헤더/라인의 복식부기 형태로 확장.

실제 고객 ERP의 export가 아니다. 매출채권/보통예금/매출만 다룬다.
원가, 세금, 기초잔액, 결산 분개는 모델링하지 않는다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

ACCOUNTS = [
    {"account_code": "1010", "account_name": "보통예금", "account_type": "자산", "normal_side": "차변"},
    {"account_code": "1100", "account_name": "매출채권", "account_type": "자산", "normal_side": "차변"},
    {"account_code": "4010", "account_name": "매출", "account_type": "수익", "normal_side": "대변"},
]
ACCOUNT_NAME = {a["account_code"]: a["account_name"] for a in ACCOUNTS}
COMPANY_CODE = "DEMO01"


def build_journals(raw: dict):
    """반환: (headers, lines) - 소스 행 12건의 매출, 입금 9건 각각 2-line.

    모든 전표가 차대변 일치하도록 기록된 모의 장부이므로
    기존 오류(중복·시점·금액 차이)는 전표 균형검사로 검출되지 않을 수 있다.
    """
    headers, lines = [], []

    def add(entry_id, doc_date, post_date, kind, source_id, invoice_id, customer, user, amount, debit_acct, credit_acct):
        assert amount > 0
        if any(h["entry_id"] == entry_id for h in headers):
            raise ValueError(f"중복 전표 ID: {entry_id}")
        doc = date.fromisoformat(doc_date)
        posting = date.fromisoformat(post_date)
        headers.append({
            "entry_id": entry_id, "company_code": COMPANY_CODE,
            "document_date": doc.isoformat(), "posting_date": posting.isoformat(),
            "fiscal_year": posting.year, "period": posting.strftime("%Y-%m"),
            "source_type": kind, "source_id": source_id, "invoice_id": invoice_id,
            "customer": customer, "currency": "KRW", "posted_by": user,
            "posting_status": "POSTED", "description": "가상 복식부기 전표",
        })
        for line_no, account_code, debit, credit in (
            (1, debit_acct, amount, 0), (2, credit_acct, 0, amount)
        ):
            lines.append({
                "entry_id": entry_id, "line_no": line_no,
                "account_code": account_code, "account_name": ACCOUNT_NAME[account_code],
                "debit_krw": debit, "credit_krw": credit,
                "description": "외상매출 인식" if kind == "SALE" else "입금으로 매출채권 감소",
            })

    invoice_issued = {v["invoice_id"]: v["issued_at"] for v in raw["invoices"]}
    for row in raw["erp"]:
        add(
            row["entry_id"], invoice_issued.get(row["invoice_id"], row["posted_at"]),
            row["posted_at"], "SALE", row["entry_id"], row["invoice_id"],
            row["customer"], row["staff"], int(row["amount"]), "1100", "4010"
        )
    for row in raw["receipts"]:
        add(
            "JR-" + row["receipt_id"], row["paid_at"], row["paid_at"],
            "RECEIPT", row["receipt_id"], row["invoice_id"], row["payer"],
            "CASHIER", int(row["amount"]), "1010", "1100"
        )
    return headers, lines


def flattened_gl(headers, lines):
    header_map = {h["entry_id"]: h for h in headers}
    if len(header_map) != len(headers):
        raise ValueError("header 전표 ID 중복")
    out = []
    for l in lines:
        h = header_map[l["entry_id"]]
        out.append({
            "entry_id": h["entry_id"], "line_no": l["line_no"],
            "company_code": h["company_code"], "document_date": h["document_date"],
            "posting_date": h["posting_date"], "fiscal_year": h["fiscal_year"],
            "period": h["period"], "source_type": h["source_type"],
            "source_id": h["source_id"], "invoice_id": h["invoice_id"],
            "account_code": l["account_code"], "account_name": l["account_name"],
            "debit_krw": l["debit_krw"], "credit_krw": l["credit_krw"],
            "currency": h["currency"], "customer": h["customer"],
            "posted_by": h["posted_by"], "memo": l["description"],
        })
    return out


def check_journal_balance(headers, lines):
    buckets = defaultdict(lambda: {"debit":0, "credit":0, "count":0})
    for line in lines:
        d, c = line["debit_krw"], line["credit_krw"]
        if d < 0 or c < 0 or (d > 0 and c > 0):
            raise ValueError("한 라인에 차변/대변 동시 양수 또는 음수는 본 실습에서 지원하지 않음")
        bucket = buckets[line["entry_id"]]
        bucket["debit"] += d
        bucket["credit"] += c
        bucket["count"] += 1
    return [{"entry_id": h["entry_id"], "debit_krw": buckets[h["entry_id"]]["debit"],
             "credit_krw": buckets[h["entry_id"]]["credit"],
             "difference_krw": buckets[h["entry_id"]]["debit"] - buckets[h["entry_id"]]["credit"],
             "line_count": buckets[h["entry_id"]]["count"],
             "check": "정상" if buckets[h["entry_id"]]["debit"] == buckets[h["entry_id"]]["credit"] and buckets[h["entry_id"]]["count"]>=2 else "검토 필요"}
            for h in headers]


def trial_balance(flat_gl, year=2025):
    totals = defaultdict(lambda: [0, 0])
    for row in flat_gl:
        if int(row["fiscal_year"]) == year:
            totals[row["account_code"]][0] += row["debit_krw"]
            totals[row["account_code"]][1] += row["credit_krw"]
    out = []
    for acc in ACCOUNTS:
        dr, cr = totals[acc["account_code"]]
        net = dr - cr
        out.append({**acc, "debit_turnover_krw": dr, "credit_turnover_krw": cr,
                    "net_debit_krw": max(net, 0), "net_credit_krw": max(-net, 0)})
    return out


def ar_by_invoice(flat_gl):
    totals = defaultdict(int)
    for row in flat_gl:
        if row["account_code"] == "1100":
            totals[row["invoice_id"]] += row["debit_krw"] - row["credit_krw"]
    return [{"invoice_id": k, "ar_balance_krw": v,
             "review_flag": "대변잔액(매출전표/선수금·미결제 검토)" if v < 0 else ("미수 잔액 있음" if v > 0 else "잔액 0")}
            for k, v in sorted(totals.items())]
