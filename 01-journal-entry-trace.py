import pandas as pd

# 1. 전표 헤더 데이터 읽기
headers = pd.read_csv(
    "data/derived/journal_headers.csv"
)

# 2. 전표 상세 데이터 읽기
lines = pd.read_csv(
    "data/derived/journal_lines.csv"
)

# 3. 데이터 확인
print("=== 전표 헤더 ===")
print(headers.head())

print("\n=== 전표 상세 ===")
print(lines.head())

print("\n=== J-1001 전표 헤더 ===")
print(headers[headers["entry_id"] == "J-1001"])

print("\n=== J-1001 전표 상세 ===")
print(lines[lines["entry_id"] == "J-1001"])

# 두 데이터 연결
merged = pd.merge(
    headers,
    lines,
    on="entry_id",
    how="inner"
)

# ① J-1001 전표만 선택
target = merged[
   merged["entry_id"] == "J-1001"
]

# ② 차변 합계
debit_total = target["debit_krw"].sum()

# ③ 대변 합계
credit_total = target["credit_krw"].sum()

print(target.to_string(index=False))
print("차변 합계:", debit_total)
print("대변 합계:", credit_total)
print("차이 금액:", debit_total - credit_total)