#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenDART 재무제표 조회 + 대사 + XBRL fact 구조 학습."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import io
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "data" / "mission11"
DART_API = "https://opendart.fss.or.kr/api"
SOURCE_GUIDE = "https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020"
REPORT_CODE_ANNUAL = "11011"

# '표준계정ID'가 일치하는 항목에만 매핑합니다. 이름만으로 추측하여 합산하지 않는다
METRIC_IDS = {
    "assets": ("BS", ("ifrs-full_Assets", "ifrs_Assets")),
    "liabilities": ("BS", ("ifrs-full_Liabilities", "ifrs_Liabilities")),
    "equity": ("BS", ("ifrs-full_Equity", "ifrs_Equity")),
    "revenue": ("IS", ("ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers", "ifrs_Revenue")),
    "operating_profit": ("IS", ("dart_OperatingIncomeLoss",)),
    "net_income": ("IS", ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss")),
}
# 손익계산서가 CIS에 통합된 회사는 IS가 없을 수 있습니다. 이 경우 CIS로 제한적으로 재탐색
INCOME_FALLBACK = {"revenue", "operating_profit", "net_income"}


def amount_or_none(value):
    """금액이 없으면 None (0으로 간주하지 않음)."""
    if value is None or str(value).strip() in {"", "-", "N/A"}:
        return None
    raw = str(value).replace(",", "").replace(" ", "")
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    try:
        return int(Decimal(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"금액 변환 실패: {value!r}") from exc


def get_api_json(key, year, corp_code, fs_div):
    qs = urlencode({
        "crtfc_key": key, "corp_code": corp_code, "bsns_year": year,
        "reprt_code": REPORT_CODE_ANNUAL, "fs_div": fs_div,
    })
    url = f"{DART_API}/fnlttSinglAcntAll.json?{qs}"
    try:
        with urlopen(url, timeout=30) as res:
            response = json.load(res)
    except (HTTPError, URLError, TimeoutError) as exc:
        # 예외 문자열에 키 포함 URL이 노출될 수 있으므로 원문 그대로 출력하지 않는다.
        raise RuntimeError("OpenDART 연결 실패. 인터넷 연결 또는 API 상태를 확인하세요.") from None
    if response.get("status") != "000":
        raise RuntimeError(f"OpenDART 응답 상태 {response.get('status')}: {response.get('message')}. "
                           "조회 가능 기간·회사코드·API 키를 확인하세요.")
    if not isinstance(response.get("list"), list) or not response["list"]:
        raise RuntimeError("OpenDART에서 빈 목록이 반환되었습니다.")
    return response


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_rows(data, source_label):
    normalized = []
    for item in data["list"]:
        row = {
            "source": source_label,
            "rcept_no": item.get("rcept_no", ""),
            "report_year": item.get("bsns_year", ""),
            "fs_div": item.get("fs_div", ""),
            "sj_div": item.get("sj_div", ""),
            "account_id": item.get("account_id", ""),
            "account_nm": item.get("account_nm", ""),
            "account_detail": item.get("account_detail", ""),
            "currency": item.get("currency", "KRW"),
            "current_amount": amount_or_none(item.get("thstrm_amount")),
            "prior_amount": amount_or_none(item.get("frmtrm_amount")),
        }
        normalized.append(row)
    return normalized


def pick_metric(rows, metric):
    statement, aliases = METRIC_IDS[metric]
    # 계정ID가 유효해도 여러 행이 있다면 함부로 합산하지 않음
    for sj in ([statement, "CIS"] if metric in INCOME_FALLBACK else [statement]):
        for alias in aliases:
            found = [r for r in rows
                     if r["sj_div"] == sj
                     and r["account_id"] == alias
                     and r["account_detail"] in ("", "-")]
            if len(found) == 1:
                return found[0], "matched"
            if len(found) > 1:
                return None, f"ambiguous: {sj}/{alias} {len(found)} rows"
    return None, "not_found (계정명만으로 자동추정하지 않음)"


def build_metrics(rows, year):
    result = []
    for metric in METRIC_IDS:
        source, status = pick_metric(rows, metric)
        result.append({
            "metric": metric, "account_id": source["account_id"] if source else "",
            "account_nm": source["account_nm"] if source else "",
            "statement": source["sj_div"] if source else "",
            "year": str(year), "current_krw": source["current_amount"] if source else None,
            "prior_year": str(year - 1), "prior_krw": source["prior_amount"] if source else None,
            "match_status": status,
        })
    return result


def build_checks(metrics):
    lookup = {r["metric"]: r for r in metrics}
    checks = []
    for period, field in (("current", "current_krw"), ("prior", "prior_krw")):
        values = [lookup[name][field] for name in ("assets", "liabilities", "equity")]
        if any(value is None for value in values):
            checks.append({"rule": "BS_EQUATION", "period": period,
                           "status": "SKIP_MISSING", "difference_krw": "",
                           "reason": "자산·부채·자본 중 확인되지 않은 계정이 있음"})
        else:
            delta = values[0] - values[1] - values[2]
            checks.append({"rule": "BS_EQUATION", "period": period,
                           "status": "PASS" if delta == 0 else "REVIEW", "difference_krw": delta,
                           "reason": "자산 = 부채 + 자본 (보고서 구성에 따른 확인 필요)"})
    revenue = lookup["revenue"]
    current, prior = revenue["current_krw"], revenue["prior_krw"]
    if current is None or prior in (None, 0):
        checks.append({"rule": "REVENUE_YOY_30PCT", "period": "current_vs_prior",
                       "status": "SKIP_MISSING", "difference_krw": "", "reason": "매출액 비교 데이터가 없거나 전기 0"})
    else:
        change = (current - prior) * 100 / prior
        checks.append({"rule": "REVENUE_YOY_30PCT", "period": "current_vs_prior",
                       "status": "REVIEW" if abs(change) >= 30 else "PASS",
                       "difference_krw": current - prior,
                       "reason": f"전년 대비 {change:+.2f}% 변화; 30%는 학습용 임의 경고 기준"})
    return checks


def local_tag(tag):
    return tag.rsplit("}", 1)[-1]


def parse_xbrl_facts(xml_bytes, source_file):
    """XBRL instance XML의 contextRef/unitRef/decimals를 읽는 입문용 파서.
    taxonomy의 정의/계산 관계·확장태그까지 검증하는 완전한 XBRL 엔진은 아닙니다.
    """
    root = ET.fromstring(xml_bytes)
    if local_tag(root.tag) != "xbrl":
        return []
    contexts = {}
    units = {}
    for el in root:
        kind = local_tag(el.tag)
        if kind == "context":
            context_id = el.attrib.get("id", "")
            period = next((x for x in el if local_tag(x.tag) == "period"), None)
            period_data = {}
            if period is not None:
                for p in period:
                    period_data[local_tag(p.tag)] = (p.text or "").strip()
            contexts[context_id] = period_data
        elif kind == "unit":
            units[el.attrib.get("id", "")] = " | ".join(
                (x.text or "").strip() for x in el.iter() if local_tag(x.tag) == "measure"
            )
    facts = []
    for el in root:
        ref = el.attrib.get("contextRef")
        if not ref:
            continue
        raw = (el.text or "").strip()
        # 숫자 fact 위주로 파악. 문자열/주석 등의 비수치 fact는 이번 입문 실습에서 제외.
        try:
            numeric = Decimal(raw)
        except (InvalidOperation, ValueError):
            continue
        context = contexts.get(ref, {})
        facts.append({
            "source_file": source_file, "concept": local_tag(el.tag),
            "namespace": el.tag.partition("}")[0].lstrip("{") if el.tag.startswith("{") else "",
            "context_ref": ref,
            "period_instant": context.get("instant", ""),
            "period_start": context.get("startDate", ""),
            "period_end": context.get("endDate", ""),
            "unit_ref": el.attrib.get("unitRef", ""),
            "unit_measure": units.get(el.attrib.get("unitRef", ""), ""),
            "decimals": el.attrib.get("decimals", ""),
            "value": str(numeric),
        })
    return facts


def fetch_xbrl_zip(key, rcept_no):
    query = urlencode({"crtfc_key": key, "rcept_no": rcept_no,
                       "reprt_code": REPORT_CODE_ANNUAL})
    url = f"{DART_API}/fnlttXbrl.xml?{query}"
    try:
        with urlopen(url, timeout=60) as res:
            binary = res.read()
    except (HTTPError, URLError, TimeoutError):
        raise RuntimeError("XBRL 원문 다운로드에 실패했습니다. 접수번호/인터넷/API 상태를 확인하세요.") from None
    if not zipfile.is_zipfile(io.BytesIO(binary)):
        try:
            msg = ET.fromstring(binary)
            status = msg.findtext("status")
            message = msg.findtext("message")
            raise RuntimeError(f"XBRL API 상태 {status}: {message} (ZIP이 아님)")
        except ET.ParseError:
            raise RuntimeError("XBRL API 응답이 ZIP이 아닙니다. 공시 XBRL 제공 여부를 확인하세요.") from None
    return binary


def facts_from_zip(binary):
    all_facts = []
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".xml", ".xbrl")):
                continue
            if info.file_size > 50 * 1024 * 1024:
                continue
            try:
                fact_rows = parse_xbrl_facts(archive.read(info), info.filename)
            except ET.ParseError:
                continue
            all_facts.extend(fact_rows)
    return all_facts


def run(mode="demo", year=2025, corp_code="00126380", fs_div="CFS", xbrl=False, rcept_no=""):
    if mode == "live":
        key = os.environ.get("DART_API_KEY", "").strip()
        if not key:
            raise RuntimeError("API 키가 없습니다. macOS: export DART_API_KEY='발급받은_키' 후 실행하세요.\n"
                               "코드·GitHub·채팅에 API 키를 공개하지 마세요.")
        if not (len(corp_code) == 8 and corp_code.isdigit()):
            raise ValueError("corp_code는 앞의 0을 포함한 8자리 문자열이어야 합니다.")
        payload = get_api_json(key, year, corp_code, fs_div)
        source = f"OpenDART 실조회 / corp_code={corp_code} / {year} 사업보고서 / {fs_div}"
        out = ROOT / "reports" / f"mission11_live_{corp_code}_{year}_{fs_div}"
    else:
        payload = json.loads((FIXTURES / "demo_opendart_response.json").read_text(encoding="utf-8"))
        source = "DEMO / 가상테크 / 임의 숫자 / 실공시 아님"
        year = 2025
        out = ROOT / "reports" / "mission11_demo"
    out.mkdir(parents=True, exist_ok=True)
    rows = normalize_rows(payload, source)
    metrics = build_metrics(rows, year)
    checks = build_checks(metrics)
    (out / "raw_api_response.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),encoding="utf-8")
    write_csv(out / "all_accounts.csv", rows,
              ["source", "rcept_no", "report_year", "fs_div", "sj_div", "account_id",
               "account_nm", "account_detail", "currency", "current_amount", "prior_amount"])
    write_csv(out / "key_metrics.csv", metrics,
              ["metric", "account_id", "account_nm", "statement", "year", "current_krw",
               "prior_year", "prior_krw", "match_status"])
    write_csv(out / "review_checks.csv", checks,
              ["rule", "period", "status", "difference_krw", "reason"])
    if mode == "demo":
        facts = parse_xbrl_facts((FIXTURES / "demo_xbrl_structure.xml").read_bytes(), "demo_xbrl_structure.xml")
    else:
        facts = []
        if xbrl:
            accession = rcept_no or next((r.get("rcept_no", "") for r in payload["list"] if r.get("rcept_no")), "")
            if not accession:
                raise RuntimeError("API 응답에서 XBRL 접수번호를 찾지 못했습니다. --rcept-no로 전달하세요.")
            binary = fetch_xbrl_zip(key, accession)
            (out / "original_xbrl.zip").write_bytes(binary)
            facts = facts_from_zip(binary)
    write_csv(out / "xbrl_facts.csv", facts,
              ["source_file", "concept", "namespace", "context_ref", "period_instant",
               "period_start", "period_end", "unit_ref", "unit_measure", "decimals", "value"])
    overview = [
        f"모드: {source}",
        f"데이터 행 수: {len(rows)}",
        f"핵심 계정 매핑: {sum(m['match_status']=='matched' for m in metrics)}/{len(metrics)}",
        f"자동 검증: {', '.join(c['rule']+'='+c['status'] for c in checks)}",
        f"XBRL 숫자 fact: {len(facts)}개 (직접 XBRL 검증과 다름)",
        "참고: 실제 기업의 내부 ERP 전표와 감사증빙은 OpenDART로 조회할 수 없습니다.",
        "주요 재무제표 검증은 공개 수치 간 일관성 확인이며 외부감사 의견이 아닙니다.",
        f"출처 문서: {SOURCE_GUIDE}",
    ]
    (out / "README_result.txt").write_text("\n".join(overview)+"\n", encoding="utf-8")
    print("=== Mission 11 | OpenDART 재무제표 + XBRL 구조 ===")
    for s in overview:
        print(s)
    print("결과 폴더:", out)
    return {"metrics": metrics, "checks": checks, "facts": facts, "output": out}


def main():
    parser = argparse.ArgumentParser(description="Mission 11 - OpenDART 재무제표 데이터 분석")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--corp-code", default="00126380", help="삼성전자 예시: 00126380")
    parser.add_argument("--fs-div", choices=("CFS", "OFS"), default="CFS")
    parser.add_argument("--xbrl", action="store_true", help="live에서 XBRL 원문 ZIP 다운로드 및 facts 파싱")
    parser.add_argument("--rcept-no", default="", help="XBRL용 14자리 접수번호 (자동 탐지 실패 시)")
    args = parser.parse_args()
    try:
        run(args.mode, args.year, args.corp_code, args.fs_div, args.xbrl, args.rcept_no)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"[실행 중단] {exc}\n")


if __name__ == "__main__":
    main()
