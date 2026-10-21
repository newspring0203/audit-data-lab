import pandas as pd

headers = pd.read_csv("data/derived/journal_headers.csv")
lines = pd.read_csv("data/derived/journal_lines.csv")
invoices = pd.read_csv("data/raw/invoices.csv")

# 1. 매출 원장 만들기
merged = pd.merge(
    headers, lines,
    on="entry_id",
    how="inner",
    validate="one_to_many"
)

# 2. 매출 계정만 선택
sales = merged[
    (merged["source_type"] == "SALE") &
    (merged["account_code"] == 4010)
].copy()

# 3. 청구서별 매출 합계
sales["net_revenue"] = (
    sales["credit_krw"] - sales["debit_krw"]
)

totals = sales.groupby("invoice_id", as_index=False)[
    "net_revenue"
].sum()

# 4. 실제 청구서와 연결
result = pd.merge(
    invoices, totals,
    left_on="청구서번호",
    right_on="invoice_id",
    how="left",
    validate="one_to_one"
)

# 5. 금액 차이 계산
result["difference"] = (
    result["net_revenue"] - result["청구금액(원)"]
)

# 6. INV-007 확인
target = result[result["청구서번호"] == "INV-007"]

print(target.to_string(index=False))

# 7. 전체 불일치 검토
errors = result[
    result["difference"].isna() |
    (result["difference"] != 0)
]

print("\n=== 검토 필요 청구서 ===")
print(errors.to_string(index=False))
