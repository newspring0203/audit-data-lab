"""가상 기업의 매출 감사 데이터 준비 및 예외 후보 식별.

이 프로그램은 감사의견이나 회계오류를 확정하지 않는다.
표준화된 원본 데이터를 바탕으로 감사인이 검토할 항목을 추출한다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import csv

SOURCES = {
    "erp": ("erp_sales.csv", {
        "전표ID": "entry_id", "청구서번호": "invoice_id",
        "기록일자": "posted_at", "고객사": "customer",
        "매출금액(원)": "amount", "담당자": "staff",
    }),
    "invoices": ("invoices.csv", {
        "청구서번호": "invoice_id", "고객사": "customer",
        "청구금액(원)": "amount", "발행일": "issued_at",
    }),
    "deliveries": ("deliveries.csv", {
        "청구서번호": "invoice_id", "고객사": "customer",
        "인도완료일": "delivered_at", "인도증빙번호": "evidence_id",
    }),
    "receipts": ("receipts.csv", {
        "입금번호": "receipt_id", "청구서번호": "invoice_id",
        "입금일자": "paid_at", "입금금액(원)": "amount",
        "입금인": "payer",
    }),
}

def load_raw(data_dir: Path) -> dict:
    out = {}
    for key, (filename, mapping) in SOURCES.items():
        with (data_dir / filename).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not set(mapping).issubset(set(reader.fieldnames or [])):
                raise ValueError(f"{filename}: 필수 컬럼이 없습니다. 필요: {list(mapping)}")
            out[key] = [
                {dst: (row[src] or "").strip() for src, dst in mapping.items()}
                for row in reader
            ]
    return out

def money(value: str) -> int:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        raise ValueError(f"금액은 정수 원이어야 합니다: {value!r}")

def parse_day(value: str):
    if not value: return None
    try: return date.fromisoformat(value)
    except ValueError: raise ValueError(f"잘못된 날짜 형식: {value!r}")

def analyze(raw: dict) -> tuple[list[dict], list[dict]]:
    """returns (transaction_register, exceptions).
    연습 가정: invoice_id당 ERP 매출기록은 1건, 1회 인도,
    VAT/할인/반품/분할인도 제외, 고객 인도일에 매출 인식.
    """
    erp_by_id = defaultdict(list)
    inv_by_id = defaultdict(list)
    delivery_by_id = defaultdict(list)
    receipts_by_id = defaultdict(list)
    for row in raw["erp"]:
        money(row["amount"]); parse_day(row["posted_at"])
        erp_by_id[row["invoice_id"]].append(row)
    for row in raw["invoices"]:
        money(row["amount"]); parse_day(row["issued_at"])
        inv_by_id[row["invoice_id"]].append(row)
    for row in raw["deliveries"]:
        parse_day(row["delivered_at"])
        delivery_by_id[row["invoice_id"]].append(row)
    for row in raw["receipts"]:
        money(row["amount"]); parse_day(row["paid_at"])
        receipts_by_id[row["invoice_id"]].append(row)

    all_ids = sorted(set(erp_by_id) | set(inv_by_id) | set(delivery_by_id) | set(receipts_by_id))
    register, exceptions = [], []

    def add(invoice_id, rule_id, assertion, finding, risk, action, amount):
        exceptions.append({
            "invoice_id": invoice_id,
            "rule_id": rule_id,
            "audit_assertion": assertion,
            "observed_fact": finding,
            "potential_risk": risk,
            "next_evidence": action,
            "potential_amount_krw": amount,
            "review_status": "검토 필요",
            "auditor_conclusion": "",  # 프로그램이 결론을 내리지 않는다
        })

    for iid in all_ids:
        erp = erp_by_id[iid]
        invoices = inv_by_id[iid]
        deliveries = delivery_by_id[iid]
        payments = receipts_by_id[iid]
        inv = invoices[0] if len(invoices) == 1 else None
        delivery = deliveries[0] if len(deliveries) == 1 else None
        booked = sum(money(r["amount"]) for r in erp)
        billed = money(inv["amount"]) if inv else None
        paid = sum(money(r["amount"]) for r in payments)
        booked_date = erp[0]["posted_at"] if len(erp) == 1 else ""
        delivered_at = delivery["delivered_at"] if delivery else ""
        register.append({
            "invoice_id": iid,
            "customer": inv["customer"] if inv else (erp[0]["customer"] if erp else ""),
            "erp_entry_count": len(erp),
            "erp_entry_ids": "; ".join(r["entry_id"] for r in erp),
            "erp_amount_krw": booked,
            "invoice_amount_krw": billed if billed is not None else "",
            "booked_at": booked_date,
            "delivered_at": delivered_at,
            "delivery_evidence_id": delivery["evidence_id"] if delivery else "",
            "receipts_count": len(payments),
            "receipts_total_krw": paid,
            "invoice_minus_receipts_krw": billed - paid if billed is not None else "",
        })
        if len(erp) > 1:
            add(iid,"R01_DUPLICATE","발생·정확성",
                f"청구서 {iid}가 ERP 전표 {len(erp)}건에 연결됨: " + ", ".join(x["entry_id"] for x in erp),
                "중복 기장 가능성(실제 분할 거래 여부 추가 확인)",
                "원전표, 취소전표, 출고 명세, 송장 단위 확인",booked)
        if inv is not None and len(erp)==1 and money(erp[0]["amount"]) != billed:
            add(iid,"R02_AMOUNT","정확성",
                f"ERP 기록액 {booked:,}원 / 청구액 {billed:,}원 / 차이 {booked-billed:+,}원",
                "매출 금액 오류 가능성",
                "계약서, 청구서 원본, 할인·수정전표 확인",abs(booked-billed))
        if erp and not deliveries:
            add(iid,"R03_NO_DELIVERY","발생·기간귀속",
                f"ERP 매출 기록 {len(erp)}건 존재 / 인도증빙 목록에 청구서 {iid}가 없음",
                "증빙 부족: 거래 미발생으로 확정할 수 없음",
                "실제 인도확인서, 운송장, 거래처 확인 요청",booked)
        if len(erp)==1 and delivery and delivered_at and parse_day(booked_date).year != parse_day(delivered_at).year:
            add(iid,"R04_CUTOFF","기간귀속",
                f"매출기록일 {booked_date} / 인도완료일 {delivered_at}",
                "연도 경계 매출 인식 시점 검토 필요",
                "계약의 통제이전 조건, 인도확인서, 결산조정 여부 확인",booked)
        if not erp and (invoices or deliveries):
            add(iid,"R05_NOT_BOOKED","완전성",
                f"청구서 {len(invoices)}건 / 인도증빙 {len(deliveries)}건 / ERP 기록 0건",
                "제공된 모집단 기준 매출 누락 가능성",
                "결산 마감 자료, 취소/반품 여부, 거래 처리 상태 확인", billed or 0)
    return register, exceptions

def analyze_files(raw_dir: Path):
    return analyze(load_raw(raw_dir))
