
import pandas as pd

# 1. 전표 헤더 CSV 파일 읽기
headers = pd.read_csv(
    "data/derived/journal_headers.csv"
)

# 2. 매출전표만 선택
sales = headers[
    headers["source_type"] == "SALE"
]

# 3. 청구서번호별 서로 다른 전표 개수 계산
counts = sales.groupby("invoice_id")[
    "entry_id"
].nunique()

# 4. 서로 다른 전표가 2건 이상 연결된 청구서 찾기
duplicates = counts[counts >= 2]

print("=== 청구서별 매출전표 개수 ===")
print(counts)

print("\n=== 중복 매출 의심 청구서 ===")
print(duplicates)

# 5. 해당 청구서와 연결된 실제 전표 조회
suspected_entries = sales[
    sales["invoice_id"].isin(duplicates.index)
]

print("\n=== 중복 의심 전표 상세 ===")
print(
    suspected_entries[
        ["entry_id", "invoice_id", "customer", "posting_date"]
    ].to_string(index=False)
)

# 6. 검증 결과 요약
print("\n검토 대상 청구서 수:", len(duplicates))
print("검토 대상 전표 수:", len(suspected_entries))