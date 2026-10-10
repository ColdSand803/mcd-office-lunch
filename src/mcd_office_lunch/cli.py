"""Command line for the office lunch planner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcd_office_lunch.mcp_client import McdMcp, McpError, find_fen, walk_records
from mcd_office_lunch.planner import plan_group_meal
from mcd_office_lunch.report import planned_to_dict, render_html, render_markdown

PAY_KEYS = ("realPayAmount", "payAmount", "totalPayAmount", "realAmount")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    names = [part.strip() for part in args.names.split(",") if part.strip()] or None
    avoid = [part.strip() for chunk in args.avoid for part in chunk.split(",") if part.strip()]
    try:
        if args.address_id or (args.store and not args.fixture and not args.meals):
            meals, promotions, assistance, demo, store_name = _live(args)
        else:
            meals, promotions, assistance, demo = _local(args)
            store_name = ""
        planned = plan_group_meal(
            meals,
            promotions,
            assistance,
            people=args.people,
            budget_yuan=args.budget,
            avoid=avoid,
            service_code=args.service or None,
            price_unit=args.price_unit,
        )
        if args.verify:
            _verify(args, planned)
        if args.place:
            _place(args, planned)
    except (McpError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(planned_to_dict(planned, names), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(planned, names=names, demo=demo, store_name=store_name))
    if args.html:
        Path(args.html).write_text(
            render_html(planned, names=names, demo=demo, store_name=store_name),
            encoding="utf-8",
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcd-office-lunch",
        description="按人数和人均预算，给企业团餐出三套方案。",
    )
    parser.add_argument("--people", type=int, default=12)
    parser.add_argument("--budget", type=float, default=35, help="人均预算，单位元")
    parser.add_argument("--fixture", help="本地菜单 JSON。用 - 表示标准输入")
    parser.add_argument("--meals", help="query-meals 的 JSON 文件")
    parser.add_argument("--promotions", help="query-promotions 的 JSON 文件")
    parser.add_argument("--assistance", help="query-meal-assistance 的 JSON 文件")
    parser.add_argument("--avoid", action="append", default=[], help="忌口词，可重复，也可用逗号")
    parser.add_argument("--names", default="", help="AA 名单，逗号分隔，人数必须一致")
    parser.add_argument("--service", default="", help="gmServiceCode")
    parser.add_argument("--address-id", default="")
    parser.add_argument("--store", default="", help="storeCode")
    parser.add_argument("--be-code", default="")
    parser.add_argument("--token", default="", help="默认读 MCD_MCP_TOKEN")
    parser.add_argument("--mcp-url", default="https://mcp.mcd.cn")
    parser.add_argument("--verify", action="store_true", help="用 calculate-price 覆盖实付")
    parser.add_argument("--html", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--price-unit", default="fen", choices=("fen", "yuan", "auto"))
    parser.add_argument("--place", default="", help="确认后下单：save、balance、lively，或 A/B/C")
    parser.add_argument("--yes", action="store_true", help="和 --place 一起用，才会真正下单")
    parser.add_argument("--remark", default="")
    parser.add_argument("--tableware", action="store_true")
    return parser


def _local(args: argparse.Namespace) -> tuple[Any, Any, Any, bool]:
    if args.meals:
        meals = _read_json(args.meals)
        promotions = _read_json(args.promotions) if args.promotions else None
        assistance = _read_json(args.assistance) if args.assistance else None
        return meals, promotions, assistance, False
    path = args.fixture or str(_default_fixture())
    demo = args.fixture is None
    blob = json.load(sys.stdin) if path == "-" else _read_json(path)
    if isinstance(blob, dict) and any(key in blob for key in ("meals", "promotions", "assistance")):
        return blob.get("meals"), blob.get("promotions"), blob.get("assistance"), demo
    return blob, None, None, demo


def _live(args: argparse.Namespace) -> tuple[Any, Any, Any, bool, str]:
    client = McdMcp(_token(args), url=args.mcp_url)
    client.initialize()
    if not args.address_id:
        raise McpError("实时查询要 --address-id。先查地址，不要把手机号写进命令历史之外的文件。")
    store_code = args.store
    be_code = args.be_code
    store_name = store_code
    if not store_code:
        listed = _stores(client.tool("delivery-query-stores", {"addressId": args.address_id, "beType": 6}))
        if not listed:
            raise McpError("这个地址没有可配送的企业团餐门店。")
        if len(listed) > 1:
            preview = "\n".join(
                f"- {item['storeCode']}  {item['name']}  beCode={item['beCode']}" for item in listed[:20]
            )
            raise McpError("有多家门店，请加上 --store 和 --be-code 再运行。\n" + preview)
        store_code = listed[0]["storeCode"]
        be_code = be_code or listed[0]["beCode"]
        store_name = listed[0]["name"]
        args.store = store_code
        args.be_code = be_code
    query = {"storeCode": store_code, "orderType": 2, "beType": 6}
    if be_code:
        query["beCode"] = be_code
    meals = client.tool("query-meals", query)
    promotions = client.tool("query-promotions", query)
    assistance_query: dict[str, Any] = {"storeCode": store_code, "orderType": 2, "beType": 6}
    if be_code:
        assistance_query["beCode"] = be_code
    assistance = client.tool("query-meal-assistance", assistance_query)
    return meals, promotions, assistance, False, store_name


def _verify(args: argparse.Namespace, planned: Any) -> None:
    if not args.store or not args.be_code:
        raise McpError("核对价格需要 --store 和 --be-code。")
    client = McdMcp(_token(args), url=args.mcp_url)
    client.initialize()
    for plan in planned.plans:
        payload: dict[str, Any] = {
            "storeCode": args.store,
            "orderType": 2,
            "beType": 6,
            "beCode": args.be_code,
            "items": [{"productCode": line.code, "quantity": line.qty} for line in plan.lines],
        }
        if args.service:
            payload["gmServiceCode"] = args.service
        quoted = client.tool("calculate-price", payload)
        amount = find_fen(quoted, PAY_KEYS)
        if amount is None:
            plan.blurb += " calculate-price 没返回实付字段，下面仍是本地估算。"
            continue
        plan.payable_fen = amount
        plan.within_budget = amount <= planned.budget_fen
        plan.blurb += " 实付已用 calculate-price 覆盖。"


def _place(args: argparse.Namespace, planned: Any) -> None:
    if not args.yes:
        raise McpError("下单被拦住了。确认方案后同时加 --place A 和 --yes。")
    if not args.address_id or not args.store or not args.be_code or not args.service:
        raise McpError("下单要齐：--address-id --store --be-code --service。")
    key = _plan_key(args.place)
    plan = next((item for item in planned.plans if item.key == key), None)
    if plan is None:
        raise McpError("方案只能是 A/B/C，或 save/balance/lively。")
    client = McdMcp(_token(args), url=args.mcp_url)
    client.initialize()
    payload = {
        "storeCode": args.store,
        "orderType": 2,
        "beType": 6,
        "beCode": args.be_code,
        "addressId": args.address_id,
        "gmServiceCode": args.service,
        "needTableware": bool(args.tableware),
        "remark": args.remark[:50],
        "items": [{"productCode": line.code, "quantity": line.qty} for line in plan.lines],
    }
    result = client.tool("create-order", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _plan_key(value: str) -> str:
    table = {
        "a": "save",
        "save": "save",
        "省钱": "save",
        "b": "balance",
        "balance": "balance",
        "均衡": "balance",
        "c": "lively",
        "lively": "lively",
        "热闹": "lively",
    }
    return table.get(value.strip().lower(), table.get(value.strip(), ""))


def _stores(payload: Any) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for node in walk_records(payload, "storeCode"):
        code = str(node.get("storeCode"))
        seen[code] = {
            "storeCode": code,
            "beCode": str(node.get("beCode") or ""),
            "name": str(node.get("storeName") or node.get("name") or node.get("shortName") or code),
        }
    return list(seen.values())


def _token(args: argparse.Namespace) -> str:
    return args.token or os.environ.get("MCD_MCP_TOKEN", "")


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _default_fixture() -> Path:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "store.json"
    if not path.exists():
        raise McpError("没找到 fixtures/store.json，请传 --fixture 或 --meals。")
    return path
