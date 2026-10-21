"""2025년 결산일 기준 매출 기간귀속(Cut-off) 검토."""

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "reports" / "mission09_cutoff_review.csv"
CLOSING_DATE = pd.Timestamp("2025-12-31")

# 1. 데이터 읽기 — 청구서 ID가 서로 다른 데이터에서 동일하게 연결되는지 검증
headers = pd.read_csv(DATA / "derived/journal_headers.csv", dtype={"invoice_id": "string"})
lines = pd.read_csv(DATA / "derived/journal_lines.csv")
invoices = pd.read_csv(DATA / "raw/invoices.csv", dtype={"청구서번호": "string"})
deliveries = pd.read_csv(DATA / "raw/deliveries.csv", dtype={"청구서번호": "string"})

# 2. 정상 전기된 매출전표의 매출 계정만 추출 (입금전표는 매출 인식과 구분)
sale_headers = headers[
    (headers["source_type"] == "SALE") &
    (headers["posting_status"] == "POSTED")
].copy()
ledger = sale_headers.merge(lines, on="entry_id", how="inner", validate="one_to_many")
sales = ledger[ledger["account_code"] == 4010].copy()
sales["posting_date"] = pd.to_datetime(sales["posting_date"], errors="raise")
sales["매출계정순액"] = sales["credit_krw"] - sales["debit_krw"]

# 3. 청구서별 매출원장 합산 — 동일 청구서에 여러 전표가 있을 수 있음
sales_summary = sales.groupby("invoice_id", as_index=False).agg(
    원장매출액=("매출계정순액", "sum"),
    전표수=("entry_id", "nunique"),
    전기일목록=("posting_date", lambda values: ", ".join(
        sorted({dt.strftime("%Y-%m-%d") for dt in values})
    )),
    관련전표=("entry_id", lambda values: ", ".join(sorted(set(values)))),
)

# 4. 실물 증빙과 대사 — 청구서 기준으로 모든 거래를 남겨서 미기록 매출도 탐지
comparison = invoices.merge(
    deliveries[["청구서번호", "인도완료일", "인도증빙번호"]],
    on="청구서번호", how="left", validate="one_to_one"
).merge(
    sales_summary, left_on="청구서번호", right_on="invoice_id",
    how="left", validate="one_to_one"
)
comparison["인도완료일"] = pd.to_datetime(comparison["인도완료일"], errors="coerce")

# 5. 기간귀속 후보 분류 — 결산일에 걸친 인식 시점 차이만 표시
#    계약상 통제가 인도 시점에 이전된다는 학습용 가정에만 적용되는 규칙.
def review(row):
    if pd.isna(row["원장매출액"]):
        return "매출 GL 미매칭 — 완전성 별도 검토"
    if pd.isna(row["인도완료일"]):
        return "인도증빙 없음 — 발생/기간귀속 확인"
    dates = [pd.Timestamp(day.strip()) for day in row["전기일목록"].split(",")]
    delivered = row["인도완료일"]
    if any(d <= CLOSING_DATE < delivered for d in dates):
        return "기간귀속 의심 — 결산 전 조기 매출 기록"
    if any(delivered <= CLOSING_DATE < d for d in dates):
        return "기간귀속 의심 — 결산 후 지연 매출 기록"
    if int(row["전표수"]) > 1:
        return "기간귀속 경고 없음 / 중복 전표 별도 검토"
    return "기간귀속 경고 없음"

comparison["검토결과"] = comparison.apply(review, axis=1)
comparison["잠재영향액_참고"] = comparison.apply(
    lambda row: int(row["원장매출액"])
    if row["검토결과"].startswith("기간귀속 의심") else "", axis=1
)
comparison["추가확인"] = comparison["검토결과"].map({
    "매출 GL 미매칭 — 완전성 별도 검토": "계약서·인도증빙·다른 계정 전표·수정/취소 여부 확인",
    "인도증빙 없음 — 발생/기간귀속 확인": "원본 인도증빙, 고객 검수·인수 기록 요청",
    "기간귀속 의심 — 결산 전 조기 매출 기록": "계약상 통제 이전일, 고객 인수일, 매출 전표의 결산 수정여부 확인",
    "기간귀속 의심 — 결산 후 지연 매출 기록": "계약상 통제 이전일, 고객 인수일, 매출 전표의 결산 수정여부 확인",
    "기간귀속 경고 없음 / 중복 전표 별도 검토": "중복 청구·수정·취소전표 여부는 Mission 03~05 참조",
    "기간귀속 경고 없음": "이번 단순 규칙에서는 연도 경계 이상 미검출(정상 확정 아님)",
})

# 6. CSV 출력 (Excel에서도 바로 열 수 있도록 BOM 포함)
columns = ["청구서번호", "고객사", "청구금액(원)", "발행일", "인도완료일", "인도증빙번호",
           "전기일목록", "관련전표", "전표수", "원장매출액", "검토결과", "잠재영향액_참고", "추가확인"]
OUT.parent.mkdir(parents=True, exist_ok=True)
comparison[columns].to_csv(OUT, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")

print("=== Mission 09 | 2025년 매출 기간귀속 검토 ===")
exceptions = comparison[comparison["검토결과"] != "기간귀속 경고 없음"]
for row in exceptions.itertuples(index=False):
    print(f"{row.청구서번호}: {row.검토결과}")
print(f"\n청구서 {len(comparison)}건 / 검토 표시 {len(exceptions)}건")
print(f"결과 CSV: {OUT}")
print("※ 의심/미매칭은 확정 회계 오류가 아닙니다. 계약 조건과 후속 증빙을 확인해야 합니다.")
