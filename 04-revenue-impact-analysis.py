
import pandas as pd

headers = pd.read_csv("data/derived/journal_headers.csv")
lines = pd.read_csv("data/derived/journal_lines.csv")

# 1. 헤더와 상세 연결
merged = pd.merge(
    headers, lines,
    on="entry_id",
    how="inner",
    validate="one_to_many"
)

# 2. INV-007과 관련된 매출 계정만 선택
target = merged[
    (merged["invoice_id"] == "INV-007") &
    (merged["account_code"] == 4010)
]

print("=== INV-007 매출 계정 ===")
print(target[
    ["entry_id", "invoice_id", "account_name",
     "debit_krw", "credit_krw"]
].to_string(index=False))

# 3. 매출 계정 순대변 금액 계산
revenue_total = (
    target["credit_krw"].sum()
    - target["debit_krw"].sum()
)

print("\n장부에 기록된 순매출:", revenue_total)
