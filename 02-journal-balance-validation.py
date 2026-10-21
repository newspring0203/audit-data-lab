import pandas as pd

# 1. CSV 파일 읽기
headers = pd.read_csv("data/derived/journal_headers.csv")
lines = pd.read_csv("data/derived/journal_lines.csv")

# 2. 전표 헤더와 상세 JOIN
merged = pd.merge(
    headers,
    lines,
    on="entry_id",
    how="inner"
)

# 3. 전표번호별 차변·대변 합계
grouped = merged.groupby("entry_id")[
    ["debit_krw", "credit_krw"]
].sum()

# 4. 차변과 대변의 차이 계산
grouped["difference"] = (
    grouped["debit_krw"] - grouped["credit_krw"]
)

# 5. 차대변 불일치 전표 추출
errors = grouped[grouped["difference"] != 0]

# 6. 결과 출력
print("\n=== 전체 전표 차대변 검증 ===")
print(grouped)

print("\n=== 차대변 불일치 전표 ===")
print(errors)

print("\n전체 전표 수:", len(grouped))
print("불일치 전표 수:", len(errors))