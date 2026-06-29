"""Build and validate jq_kb eval datasets (full corpus only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.jq_kb.chunkers.jq_dict import static_suffix_records
from app.core.jq_kb.paths import EVAL_DATA_DIR, JQ_DICT_RAW_DIR, JQ_STRATEGY_RAW_DIR

JQ_API_EVAL = EVAL_DATA_DIR / "jq_api_eval.jsonl"
JQ_DICT_EVAL = EVAL_DATA_DIR / "jq_dict_eval.jsonl"
JQ_STRATEGY_EVAL = EVAL_DATA_DIR / "jq_strategy_eval.jsonl"

DICT_QUESTIONS: list[dict[str, str]] = [
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

STRATEGY_QUESTIONS: list[dict[str, str]] = [
    {"id": "s001", "query": "ETF轮动策略入门", "title": "ETF轮动策略-入门2.0", "category": "etf", "difficulty": "easy"},
    {"id": "s002", "query": "ETF动量轮动 MA乖离择时", "title": "ETF动量轮动MA乖离择时", "category": "etf", "difficulty": "medium"},
    {"id": "s003", "query": "国债ETF增强控制回撤", "title": "ETF-控制回撤性能拉满（国债ETF增强）", "category": "etf", "difficulty": "medium"},
    {"id": "s004", "query": "场内基金定投价值平均", "title": "场内基金定投价值平均增强策略，年化30%+", "category": "etf", "difficulty": "medium"},
    {"id": "s005", "query": "龙头首阴战法", "title": "龙头首阴战法改版二", "category": "stock", "difficulty": "easy"},
    {"id": "s006", "query": "BOLL择时策略", "title": "近几年一直有效的股票BOLL择时策略", "category": "timing", "difficulty": "easy"},
    {"id": "s007", "query": "集合竞价量比策略", "title": "集合竞价量比策略V1", "category": "auction", "difficulty": "medium"},
    {"id": "s008", "query": "initialize 函数 set_benchmark 沪深300", "title": "价值策略重开，再次向Jqz1226致敬", "category": "code", "difficulty": "hard"},
]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _load_dict_corpus() -> set[str]:
    full_path = JQ_DICT_RAW_DIR / "full.json"
    if not full_path.is_file():
        raise FileNotFoundError(full_path)
    data = json.loads(full_path.read_text(encoding="utf-8"))
    entities = data.get("entities", data if isinstance(data, list) else [])
    codes = {str(e["code"]) for e in entities if e.get("code")}
    codes.update(s["code"] for s in static_suffix_records())
    return codes


def ensure_dict_eval_dataset() -> Path:
    corpus = _load_dict_corpus()
    missing = [q["id"] for q in DICT_QUESTIONS if q["expected_code"] not in corpus]
    if missing:
        raise ValueError(f"dict eval expected_code missing from corpus: {missing}")
    _write_jsonl(JQ_DICT_EVAL, DICT_QUESTIONS)
    return JQ_DICT_EVAL


def ensure_strategy_eval_dataset() -> Path:
    posts_path = JQ_STRATEGY_RAW_DIR / "posts.json"
    if not posts_path.is_file():
        raise FileNotFoundError(posts_path)
    posts = json.loads(posts_path.read_text(encoding="utf-8"))["posts"]
    title_to_pid = {p["title"]: int(p["post_id"]) for p in posts}
    rows: list[dict[str, Any]] = []
    for q in STRATEGY_QUESTIONS:
        pid = title_to_pid.get(q["title"])
        if not pid:
            raise ValueError(f"strategy eval title not in posts.json: {q['title']}")
        rows.append(
            {
                "id": q["id"],
                "query": q["query"],
                "expected_post_id": pid,
                "category": q["category"],
                "difficulty": q["difficulty"],
            }
        )
    _write_jsonl(JQ_STRATEGY_EVAL, rows)
    return JQ_STRATEGY_EVAL


def ensure_eval_datasets() -> dict[str, Path]:
    if not JQ_API_EVAL.is_file():
        raise FileNotFoundError(
            f"Missing {JQ_API_EVAL}. Commit jq_api_eval.jsonl or restore from eval/datasets."
        )
    return {
        "jq_api": JQ_API_EVAL,
        "jq_dict": ensure_dict_eval_dataset(),
        "jq_strategy": ensure_strategy_eval_dataset(),
    }
