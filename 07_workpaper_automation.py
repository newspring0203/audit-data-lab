from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUTPUT = BASE / "reports" / "mission07_audit_workpaper.xlsx"

# 1) 감사팀이 전달받았다고 가정한 3개 데이터 파일 읽기
headers = pd.read_csv(DATA / "derived/journal_headers.csv", dtype={"invoice_id": "string"})
lines = pd.read_csv(DATA / "derived/journal_lines.csv")
invoices = pd.read_csv(DATA / "raw/invoices.csv", dtype={"청구서번호": "string"})

# 2) 전표 헤더와 상세 JOIN → 매출 계정(4010)의 금액만 추출
ledger = pd.merge(headers, lines, on="entry_id", how="inner", validate="one_to_many")
sales = ledger[(ledger["source_type"] == "SALE") & (ledger["account_code"] == 4010)].copy()
sales["net_revenue"] = sales["credit_krw"] - sales["debit_krw"]

# 3) 청구서번호 기준으로 매출금액과 연결된 전표번호 집계
sales_summary = sales.groupby("invoice_id", as_index=False).agg(
    장부매출액=("net_revenue", "sum"),
    전표수=("entry_id", "nunique"),
    관련전표=("entry_id", lambda s: ", ".join(sorted(s.unique())))
)

# 4) 양방향 대사: 청구서만 있거나 GL에만 있는 경우도 놓치지 않도록 outer JOIN
comparison = pd.merge(
    invoices.rename(columns={"청구금액(원)": "청구금액"}),
    sales_summary,
    left_on="청구서번호", right_on="invoice_id",
    how="outer", validate="one_to_one", indicator=True
)
comparison["청구서번호"] = comparison["청구서번호"].fillna(comparison["invoice_id"])
comparison["차이금액"] = comparison["장부매출액"] - comparison["청구금액"]


def classify(row):
    """데이터로 확인한 예외만 표시. 회계 오류 확정은 하지 않음."""
    if row["_merge"] == "left_only":
        return "청구서만 존재(GL 미매칭)"
    if row["_merge"] == "right_only":
        return "원장만 존재(청구서 미매칭)"
    if row["전표수"] >= 2:
        return "중복 전표 참조" + (" + 금액 불일치" if row["차이금액"] != 0 else "")
    if row["차이금액"] != 0:
        return "금액 불일치"
    return "일치"


comparison["검토상태"] = comparison.apply(classify, axis=1)
comparison = comparison.sort_values("청구서번호").reset_index(drop=True)
exceptions = comparison[comparison["검토상태"] != "일치"].copy()

# 5) 감사검토조서: 관찰 사실과 감사 판단(가설)을 명확하게 구분

def workpaper_note(row):
    invoice = row["청구서번호"]
    if row["_merge"] == "left_only":
        return pd.Series([
            "청구서는 있지만 제공된 매출 GL에서 일치 전표를 찾지 못함",
            "완전성 검토(매출 인식 요건 충족 여부는 별도 판단)",
            "청구서 원본, 고객 인수/인도 증빙, 다른 계정 전표, 취소·수정 전표"
        ])
    if row["_merge"] == "right_only":
        return pd.Series([
            "매출 GL 전표는 있지만 제공된 청구서 목록에 대응 항목이 없음",
            "발생·정확성 및 증빙 누락 여부 검토",
            "청구서 원본, 계약서, 인도증빙, 청구서 목록의 완전성"
        ])
    if row["전표수"] >= 2:
        return pd.Series([
            f"청구서 {invoice}에 매출 전표 {int(row['전표수'])}건 연결; 차이 {int(row['차이금액']):,}원",
            "중복 매출 가능성(분할 기장·수정·취소 전표 여부 확인)",
            "원본 청구서, 각 전표의 상세/취소 내역, 계약서, 인도증빙"
        ])
    return pd.Series([
        f"청구서와 장부 매출 금액의 차이 {int(row['차이금액']):,}원",
        "매출금액 정확성 검토(추가 청구·할인·수정 전표 여부 확인)",
        "계약서, 원본/수정 청구서, 거래명세서, 매출·수정 전표"
    ])


exceptions[["확인된사실", "감사상검토사항", "추가요청증빙"]] = exceptions.apply(workpaper_note, axis=1)
exceptions["감사인검토의견"] = ""  # 사람이 입력
exceptions["최종결론"] = "판단 보류"

# 6) Excel 파일에 [요약 / 전체 대사 / 예외 검토조서] 3개 시트 작성
summary = pd.DataFrame([
    ["대사 청구서 수", len(invoices)],
    ["매출 GL 전표 수", sales["entry_id"].nunique()],
    ["검토 대상 청구서 수", len(exceptions)],
    ["금액 차이(매칭된 거래만, 순차이)", int(comparison["차이금액"].dropna().sum())],
    ["분석 범위", "가상 데이터 / 청구서-매출원장 대사 한정"],
    ["주의", "차이 금액은 확정 오류액이 아니며, 인도증빙·기간귀속은 이 단계에서 검사하지 않음"],
], columns=["항목", "결과"])

comparison_export = comparison.drop(columns=["invoice_id", "_merge", "비고", "발행일"], errors="ignore")
review_export = exceptions[[
    "청구서번호", "고객사", "관련전표", "청구금액", "장부매출액", "차이금액",
    "검토상태", "확인된사실", "감사상검토사항", "추가요청증빙",
    "감사인검토의견", "최종결론"
]]

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
    summary.to_excel(writer, sheet_name="00_요약", index=False)
    comparison_export.to_excel(writer, sheet_name="01_전체대사", index=False)
    review_export.to_excel(writer, sheet_name="02_감사검토조서", index=False)

print("=== Mission 07 감사검토조서 자동 생성 ===")
print(review_export[["청구서번호", "검토상태", "차이금액"]].to_string(index=False))
print(f"\n검토 대상 {len(exceptions)}건 / 저장 위치: {OUTPUT}")
