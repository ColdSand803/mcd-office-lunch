"""Pick three group-meal plans inside a per-person budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from mcd_office_lunch.catalog import Product, extract_products
from mcd_office_lunch.promotions import Discount, Line, Promotion, apply_best, extract_promotions

STYLES: tuple[tuple[str, str, str], ...] = (
    ("save", "省钱", "每人同款。能凑齐主食、小食、饮料时，取得实付最低的一档。"),
    ("balance", "均衡", "凑齐三样，总价靠近预算但留一点余量。"),
    ("lively", "热闹", "仍在预算内，把主食和小食往上换。"),
)


@dataclass(frozen=True)
class Share:
    name: str
    fen: int


@dataclass
class Plan:
    key: str
    title: str
    blurb: str
    lines: list[Line]
    food_fen: int
    discount: Discount
    assistance_fen: int
    payable_fen: int
    within_budget: bool


@dataclass
class Planned:
    people: int
    budget_per_fen: int
    budget_fen: int
    plans: list[Plan]
    assistance_name: str
    warnings: list[str] = field(default_factory=list)


def yuan_to_fen(yuan: float | str | Decimal) -> int:
    return int((Decimal(str(yuan)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_yuan(fen: int) -> str:
    sign = "-" if fen < 0 else ""
    fen = abs(int(fen))
    return f"{sign}{fen // 100}.{fen % 100:02d}"


def split_even(total_fen: int, people: int, names: list[str] | None = None) -> list[Share]:
    if people <= 0:
        raise ValueError("人数要大于 0")
    if names and len(names) != people:
        raise ValueError("名单人数和用餐人数不一致")
    labels = names if names else [f"第{index + 1}人" for index in range(people)]
    base, remainder = divmod(int(total_fen), people)
    return [
        Share(name=labels[index], fen=base + (1 if index < remainder else 0))
        for index in range(people)
    ]


def plan_group_meal(
    meals: Any,
    promotions: Any = None,
    assistance: Any = None,
    *,
    people: int,
    budget_yuan: float | str,
    avoid: list[str] | None = None,
    service_code: str | None = None,
    price_unit: str = "fen",
) -> Planned:
    if people < 1 or people > 200:
        raise ValueError("人数要在 1 到 200 之间")
    budget_per = yuan_to_fen(budget_yuan)
    if budget_per <= 0:
        raise ValueError("人均预算要大于 0")
    products = _filter_products(extract_products(meals, price_unit=price_unit), avoid or [])
    if not products:
        raise ValueError("菜单里没有可用餐品。检查忌口词，或确认 query-meals 有价格。")
    rules = extract_promotions(promotions) if promotions is not None else []
    service_name, service_fen = _assistance_fee(assistance, service_code)
    carts = _carts(products, people, rules, service_fen)
    if not carts:
        raise ValueError("这些餐品组不出购物车")
    budget = budget_per * people
    chosen = _choose(carts, budget)
    warnings: list[str] = []
    if service_code and service_name == "":
        warnings.append(f"没有找到助餐服务 {service_code}，这次按不加服务费计算。")
    if not service_code:
        warnings.append("还没选助餐服务。配送费或入室服务以门店返回为准。")
    if not rules:
        warnings.append("没有读到满减规则，金额只是餐品标价合计。")
    warnings.append("促销只取优惠更大的一条，不叠加。展示前要用 calculate-price 覆盖实付。")
    plans = [
        _to_plan(key, title, blurb, cart, budget)
        for (key, title, blurb), cart in zip(STYLES, chosen, strict=True)
    ]
    return Planned(
        people=people,
        budget_per_fen=budget_per,
        budget_fen=budget,
        plans=plans,
        assistance_name=service_name,
        warnings=warnings,
    )


@dataclass
class _Cart:
    lines: list[Line]
    food_fen: int
    discount: Discount
    assistance_fen: int

    @property
    def payable_fen(self) -> int:
        return self.food_fen - self.discount.amount_fen + self.assistance_fen

    @property
    def roles(self) -> int:
        return len({line.role for line in self.lines if line.qty > 0})

    @property
    def signature(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted((line.code, line.qty) for line in self.lines))


def _filter_products(products: list[Product], avoid: list[str]) -> list[Product]:
    words = [word.strip() for word in avoid if word and word.strip()]
    if not words:
        return products
    return [item for item in products if not any(word in item.name for word in words)]


def _carts(
    products: list[Product],
    people: int,
    rules: list[Promotion],
    assistance_fen: int,
) -> list[_Cart]:
    mains = _cap([item for item in products if item.role == "main"])
    if not mains:
        mains = _cap([item for item in products if item.role == "other"] or products)
    sides = _cap([item for item in products if item.role == "side"])
    drinks = _cap([item for item in products if item.role == "drink"])
    carts: list[_Cart] = []
    seen: set[tuple[tuple[str, int], ...]] = set()
    for main in mains:
        complete = "套餐" in main.name or "全餐" in main.name
        side_options = (None,) if complete else (None, *sides)
        drink_options = (None,) if complete else (None, *drinks)
        for side in side_options:
            for drink in drink_options:
                lines = [_line(main, people)]
                if side is not None:
                    lines.append(_line(side, people))
                if drink is not None:
                    lines.append(_line(drink, people))
                cart = _price(lines, rules, assistance_fen)
                if cart.signature in seen:
                    continue
                seen.add(cart.signature)
                carts.append(cart)
    return carts


def _cap(items: list[Product], limit: int = 12) -> list[Product]:
    if len(items) <= limit:
        return items
    ordered = sorted(items, key=lambda item: (item.price_fen, item.code))
    picked = {item.code: item for item in ordered[:8] + ordered[-4:]}
    return list(picked.values())


def _line(product: Product, qty: int) -> Line:
    return Line(
        code=product.code,
        name=product.name,
        role=product.role,
        qty=qty,
        unit_fen=product.price_fen,
    )


def _price(lines: list[Line], rules: list[Promotion], assistance_fen: int) -> _Cart:
    food = sum(line.subtotal_fen for line in lines)
    discount = apply_best(lines, rules)
    return _Cart(lines=lines, food_fen=food, discount=discount, assistance_fen=assistance_fen)


def _choose(carts: list[_Cart], budget: int) -> list[_Cart]:
    used: set[tuple[tuple[str, int], ...]] = set()
    chosen: list[_Cart] = []
    for key, _title, _blurb in STYLES:
        ranked = sorted(carts, key=lambda cart: _rank(key, cart, budget))
        pick = next((cart for cart in ranked if cart.signature not in used), ranked[0])
        used.add(pick.signature)
        chosen.append(pick)
    return chosen


def _rank(style: str, cart: _Cart, budget: int) -> tuple:
    over = 0 if cart.payable_fen <= budget else 1
    if style == "save":
        return (over, -cart.roles, cart.payable_fen, cart.signature)
    if style == "balance":
        target = (budget * 9) // 10
        distance = abs(cart.payable_fen - target)
        above_target = 0 if cart.payable_fen <= target else 1
        return (over, -cart.roles, distance, above_target, cart.payable_fen, cart.signature)
    return (over, -cart.roles, -cart.payable_fen, cart.signature)


def _to_plan(key: str, title: str, blurb: str, cart: _Cart, budget: int) -> Plan:
    return Plan(
        key=key,
        title=title,
        blurb=blurb,
        lines=list(cart.lines),
        food_fen=cart.food_fen,
        discount=cart.discount,
        assistance_fen=cart.assistance_fen,
        payable_fen=cart.payable_fen,
        within_budget=cart.payable_fen <= budget,
    )


def _assistance_fee(payload: Any, service_code: str | None) -> tuple[str, int]:
    if not service_code or payload is None:
        return "", 0
    match = _find_service(payload, service_code)
    if match is None:
        return "", 0
    name = str(match.get("name") or match.get("serviceName") or service_code)
    for key in ("priceFen", "feeFen", "amountFen"):
        if key in match:
            return name, money_or_zero(match.get(key), "fen")
    for key in ("price", "fee", "amount"):
        if key in match:
            unit = match.get("priceUnit") or match.get("unit")
            return name, money_or_zero(match.get(key), None if unit is None else str(unit))
    return name, 0


def money_or_zero(value: Any, unit: str | None) -> int:
    from mcd_office_lunch.catalog import money_to_fen

    parsed = money_to_fen(value, unit)
    return 0 if parsed is None else parsed


def _find_service(node: Any, service_code: str) -> dict[str, Any] | None:
    if isinstance(node, dict):
        code = node.get("gmServiceCode") or node.get("serviceCode") or node.get("code")
        if str(code) == service_code and any(key in node for key in ("name", "serviceName", "price", "priceFen", "fee")):
            return node
        for value in node.values():
            found = _find_service(value, service_code)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_service(value, service_code)
            if found is not None:
                return found
    return None
