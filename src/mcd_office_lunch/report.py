"""Text and HTML renderers for a three-plan group meal."""

from __future__ import annotations

import html
from mcd_office_lunch.planner import Planned, Plan, format_yuan, split_even

_LETTERS = ("A", "B", "C")


def render_markdown(
    planned: Planned,
    *,
    names: list[str] | None = None,
    demo: bool = False,
    store_name: str = "",
) -> str:
    lines: list[str] = []
    where = f" · {store_name}" if store_name else ""
    lines.append(
        f"# 团餐操盘手{where}"
    )
    lines.append("")
    lines.append(
        f"{planned.people} 人 · 人均预算 {format_yuan(planned.budget_per_fen)} 元 · "
        f"预算合计 {format_yuan(planned.budget_fen)} 元"
    )
    if planned.assistance_name:
        lines.append(f"助餐服务：{planned.assistance_name}")
    if demo:
        lines.append("")
        lines.append("> 下面是仓库里的演示菜单，用来看方案形状。真实点餐必须换成门店的 query-meals 和 query-promotions。")
    lines.append("")
    for letter, plan in zip(_LETTERS, planned.plans, strict=False):
        lines.extend(_plan_markdown(letter, plan, planned.people, names))
    if planned.warnings:
        lines.append("## 注意")
        lines.append("")
        for warning in planned.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append("回复「下单 A」或「下单 B」「下单 C」才会创建订单。没确认之前不会下单。")
    lines.append("")
    return "\n".join(lines)


def render_html(
    planned: Planned,
    *,
    names: list[str] | None = None,
    demo: bool = False,
    store_name: str = "",
) -> str:
    cards = []
    for letter, plan in zip(_LETTERS, planned.plans, strict=False):
        cards.append(_plan_html(letter, plan, planned.people, names))
    note = ""
    if demo:
        note = "<p class=\"demo\">演示菜单，不是门店实时价。</p>"
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in planned.warnings)
    title = "团餐操盘手" + (f" · {html.escape(store_name)}" if store_name else "")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; background: #fff6e8; color: #24180f; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }}
  main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 48px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .meta {{ margin: 0 0 20px; font-size: 18px; }}
  .demo {{ background: #fff; border-left: 6px solid #ffc72c; padding: 10px 12px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
  article {{ background: #fff; border-radius: 18px; padding: 16px; box-shadow: 0 8px 24px rgba(80, 30, 0, 0.08); }}
  .letter {{ display: inline-block; background: #c8102e; color: #fff; border-radius: 999px; padding: 2px 10px; font-weight: 700; }}
  .pay {{ font-size: 40px; margin: 8px 0 0; font-variant-numeric: tabular-nums; }}
  .sub {{ color: #6b5344; margin: 0 0 12px; }}
  ul {{ padding-left: 18px; }}
  .over {{ color: #c8102e; font-weight: 700; }}
  footer {{ margin-top: 20px; color: #6b5344; font-size: 14px; }}
</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <p class="meta">{planned.people} 人 · 人均预算 {format_yuan(planned.budget_per_fen)} 元 · 合计 {format_yuan(planned.budget_fen)} 元</p>
  {note}
  <section class="grid">
    {''.join(cards)}
  </section>
  <ul>{warnings}</ul>
  <footer>非官方粉丝作品。回复「下单 A / B / C」才会创建订单。金额单位在接口里是分，这里已换成元。</footer>
</main>
</body>
</html>
"""


def planned_to_dict(planned: Planned, names: list[str] | None = None) -> dict:
    return {
        "people": planned.people,
        "budgetPerFen": planned.budget_per_fen,
        "budgetFen": planned.budget_fen,
        "assistance": planned.assistance_name,
        "warnings": planned.warnings,
        "plans": [_plan_dict(letter, plan, planned.people, names) for letter, plan in zip(_LETTERS, planned.plans)],
    }


def _plan_markdown(letter: str, plan: Plan, people: int, names: list[str] | None) -> list[str]:
    flag = "" if plan.within_budget else " · 超预算"
    shares = split_even(plan.payable_fen, people, names)
    per = shares[0].fen
    same = all(share.fen == per for share in shares)
    lines = [
        f"## 方案 {letter} · {plan.title}{flag}",
        "",
        plan.blurb,
        "",
        "| 餐品 | 数量 | 单价 | 小计 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in plan.lines:
        lines.append(
            f"| {item.name} | {item.qty} | {format_yuan(item.unit_fen)} | {format_yuan(item.subtotal_fen)} |"
        )
    lines.extend(
        [
            "",
            f"- 餐品小计：{format_yuan(plan.food_fen)} 元",
            f"- 优惠：{plan.discount.label}（-{format_yuan(plan.discount.amount_fen)} 元）",
            f"- 助餐服务：{format_yuan(plan.assistance_fen)} 元",
            f"- 预计实付：{format_yuan(plan.payable_fen)} 元",
        ]
    )
    if same:
        lines.append(f"- AA：每人 {format_yuan(per)} 元")
    else:
        rich = "、".join(share.name for share in shares if share.fen == per)
        lines.append(
            f"- AA：{rich} 各 {format_yuan(per)} 元，其余 {format_yuan(per - 1)} 元。加总等于实付。"
        )
    lines.append("")
    return lines


def _plan_html(letter: str, plan: Plan, people: int, names: list[str] | None) -> str:
    shares = split_even(plan.payable_fen, people, names)
    items = "".join(
        f"<li>{html.escape(item.name)} × {item.qty} · {format_yuan(item.subtotal_fen)} 元</li>"
        for item in plan.lines
    )
    flag = "" if plan.within_budget else " <span class=\"over\">超预算</span>"
    return (
        "<article>"
        f"<span class=\"letter\">{letter}</span> <strong>{html.escape(plan.title)}</strong>{flag}"
        f"<p class=\"pay\">{format_yuan(plan.payable_fen)}<span style=\"font-size:16px\"> 元</span></p>"
        f"<p class=\"sub\">人均 {format_yuan(shares[0].fen)} 元起 · {html.escape(plan.discount.label)}</p>"
        f"<ul>{items}</ul>"
        "</article>"
    )


def _plan_dict(letter: str, plan: Plan, people: int, names: list[str] | None) -> dict:
    shares = split_even(plan.payable_fen, people, names)
    return {
        "letter": letter,
        "key": plan.key,
        "title": plan.title,
        "blurb": plan.blurb,
        "withinBudget": plan.within_budget,
        "foodFen": plan.food_fen,
        "discountFen": plan.discount.amount_fen,
        "discountLabel": plan.discount.label,
        "assistanceFen": plan.assistance_fen,
        "payableFen": plan.payable_fen,
        "lines": [
            {
                "productCode": item.code,
                "name": item.name,
                "quantity": item.qty,
                "unitFen": item.unit_fen,
            }
            for item in plan.lines
        ],
        "shares": [{"name": share.name, "fen": share.fen} for share in shares],
    }
