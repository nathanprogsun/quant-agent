"""Build jq_dict eval datasets from raw/full.json.

Every ``expected_code`` is validated against the crawled corpus plus static
suffixes merged at ingest time. Regenerate after crawl/ingest updates::

    cd backend
    uv run python scripts/build_eval_jq_dict.py --mode all --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.chunkers.jq_dict import static_suffix_records
from app.core.jq_kb.paths import EVAL_DATA_DIR, JQ_DICT_RAW_DIR

PILOT_OUT = EVAL_DATA_DIR / "jq_dict_eval_pilot.jsonl"
FULL_OUT = EVAL_DATA_DIR / "jq_dict_eval_full.jsonl"
FULL_JSON = JQ_DICT_RAW_DIR / "full.json"

# Hand-authored queries aligned to codes in full.json (not legacy pilot guesses).
PILOT_QUESTIONS: list[dict[str, str]] = [
    {"id": "d001", "query": "申万农林牧渔一级行业代码", "expected_code": "801010", "category": "industry", "difficulty": "medium"},
    {"id": "d002", "query": "HY001 对应什么聚宽行业", "expected_code": "HY001", "category": "industry", "difficulty": "easy"},
    {"id": "d003", "query": "申万医药生物行业代码", "expected_code": "801150", "category": "industry", "difficulty": "medium"},
    {"id": "d004", "query": "人工智能概念板块代码", "expected_code": "GN201", "category": "concept", "difficulty": "medium"},
    {"id": "d005", "query": "GN039 是什么概念", "expected_code": "GN039", "category": "concept", "difficulty": "easy"},
    {"id": "d006", "query": "锂电池概念代码", "expected_code": "GN039", "category": "concept", "difficulty": "easy"},
    {"id": "d007", "query": "半导体概念代码", "expected_code": "GN878", "category": "concept", "difficulty": "medium"},
    {"id": "d008", "query": "沪深300指数代码", "expected_code": "000300.XSHG", "category": "index", "difficulty": "easy"},
    {"id": "d009", "query": "中证500指数代码", "expected_code": "000905.XSHG", "category": "index", "difficulty": "easy"},
    {"id": "d010", "query": "创业板指代码", "expected_code": "399006.XSHE", "category": "index", "difficulty": "easy"},
    {"id": "d011", "query": "close 收盘价字段", "expected_code": "close", "category": "field", "difficulty": "easy"},
    {"id": "d012", "query": "开盘价 open 字段", "expected_code": "open", "category": "field", "difficulty": "easy"},
    {"id": "d013", "query": "pe_ratio 市盈率字段", "expected_code": "pe_ratio", "category": "field", "difficulty": "easy"},
    {"id": "d014", "query": "成交量 volume 字段", "expected_code": "volume", "category": "field", "difficulty": "easy"},
    {"id": "d015", "query": "MACD 技术指标", "expected_code": "MACD", "category": "field", "difficulty": "medium"},
    {"id": "d016", "query": "alpha_001 Alpha101因子", "expected_code": "alpha_001", "category": "field", "difficulty": "medium"},
    {"id": "d017", "query": "上证指数代码", "expected_code": "000001.XSHG", "category": "index", "difficulty": "easy"},
    {"id": "d018", "query": "上海证券交易所代码后缀", "expected_code": ".XSHG", "category": "suffix", "difficulty": "easy"},
    {"id": "d019", "query": ".XSHE 是什么后缀", "expected_code": ".XSHE", "category": "suffix", "difficulty": "easy"},
    {"id": "d020", "query": "公募基金代码后缀", "expected_code": ".OF", "category": "suffix", "difficulty": "easy"},
]

FULL_EXTRA_QUESTIONS: list[dict[str, str]] = [
    {"id": "d021", "query": "GN028 智能电网概念", "expected_code": "GN028", "category": "concept", "difficulty": "easy"},
    {"id": "d022", "query": "新能源概念板块代码", "expected_code": "GN035", "category": "concept", "difficulty": "easy"},
    {"id": "d023", "query": "迪士尼概念代码", "expected_code": "GN032", "category": "concept", "difficulty": "medium"},
    {"id": "d024", "query": "HY006 医疗保健行业", "expected_code": "HY006", "category": "industry", "difficulty": "easy"},
    {"id": "d025", "query": "证监会医药制造业行业代码", "expected_code": "C27", "category": "industry", "difficulty": "hard"},
    {"id": "d026", "query": "上证180指数代码", "expected_code": "000010.XSHG", "category": "index", "difficulty": "medium"},
    {"id": "d027", "query": "科创50指数代码", "expected_code": "000688.XSHG", "category": "index", "difficulty": "medium"},
    {"id": "d028", "query": "最高价 high 字段", "expected_code": "high", "category": "field", "difficulty": "easy"},
    {"id": "d029", "query": "成交额 money 字段", "expected_code": "money", "category": "field", "difficulty": "easy"},
    {"id": "d030", "query": "beta 贝塔因子", "expected_code": "beta", "category": "field", "difficulty": "medium"},
    {"id": "d031", "query": "momentum 动量因子", "expected_code": "momentum", "category": "field", "difficulty": "medium"},
    {"id": "d032", "query": "宏观数据统计季度字段", "expected_code": "stat_quarter", "category": "field", "difficulty": "hard"},
    {"id": "d033", "query": "应付债券 bonds_payable", "expected_code": "bonds_payable", "category": "field", "difficulty": "hard"},
    {"id": "d034", "query": "RSI 相对强弱指标", "expected_code": "RSI", "category": "field", "difficulty": "medium"},
    {"id": "d035", "query": "南方积配基金代码", "expected_code": "160105.XSHE", "category": "fund", "difficulty": "medium"},
    {"id": "d036", "query": "参股金融概念 GN001", "expected_code": "GN001", "category": "concept", "difficulty": "easy"},
    {"id": "d037", "query": "换手率相对波动率因子", "expected_code": "turnover_volatility", "category": "field", "difficulty": "hard"},
    {"id": "d038", "query": "alpha_101 因子代码", "expected_code": "alpha_101", "category": "field", "difficulty": "medium"},
    {"id": "d039", "query": "中金所期货代码后缀", "expected_code": ".CCFX", "category": "suffix", "difficulty": "medium"},
    {"id": "d040", "query": "智能电网概念板块", "expected_code": "GN028", "category": "concept", "difficulty": "easy"},
]


def load_corpus_codes(full_path: Path = FULL_JSON) -> set[str]:
    if not full_path.is_file():
        raise FileNotFoundError(full_path)
    data = json.loads(full_path.read_text(encoding="utf-8"))
    entities = data.get("entities", data if isinstance(data, list) else [])
    codes = {str(e["code"]) for e in entities if e.get("code")}
    codes.update(s["code"] for s in static_suffix_records())
    return codes


def _validate_questions(questions: list[dict[str, str]], corpus: set[str]) -> None:
    missing: list[str] = []
    for q in questions:
        code = q["expected_code"]
        if code not in corpus:
            missing.append(f"{q['id']}: {code}")
    if missing:
        raise ValueError(
            "expected_code not in full.json (+ static suffixes):\n  "
            + "\n  ".join(missing)
        )


def _write_jsonl(path: Path, questions: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(q, ensure_ascii=False) for q in questions]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_pilot(corpus: set[str]) -> list[dict[str, str]]:
    _validate_questions(PILOT_QUESTIONS, corpus)
    return list(PILOT_QUESTIONS)


def build_full(corpus: set[str]) -> list[dict[str, str]]:
    all_q = [*PILOT_QUESTIONS, *FULL_EXTRA_QUESTIONS]
    _validate_questions(all_q, corpus)
    return all_q


def main() -> None:
    parser = argparse.ArgumentParser(description="Build jq_dict eval datasets from full.json")
    parser.add_argument("--mode", choices=["pilot", "full", "all"], default="all")
    parser.add_argument("--force", action="store_true", help="Overwrite existing jsonl files")
    args = parser.parse_args()

    corpus = load_corpus_codes()
    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode in ("pilot", "all"):
        if PILOT_OUT.is_file() and not args.force:
            print(f"Pilot exists (use --force): {PILOT_OUT}")
        else:
            pilot = build_pilot(corpus)
            _write_jsonl(PILOT_OUT, pilot)
            print(f"Wrote {PILOT_OUT} ({len(pilot)} questions)")

    if args.mode in ("full", "all"):
        if FULL_OUT.is_file() and not args.force:
            print(f"Full exists (use --force): {FULL_OUT}")
        else:
            full = build_full(corpus)
            _write_jsonl(FULL_OUT, full)
            print(f"Wrote {FULL_OUT} ({len(full)} questions)")

    print(f"Corpus codes validated against: {FULL_JSON} ({len(corpus)} codes)")


if __name__ == "__main__":
    main()
