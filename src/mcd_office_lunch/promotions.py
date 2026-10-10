"""Apply one store promotion to a cart. Rules are not stacked."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from mcd_office_lunch.catalog import money_to_fen

_THRESHOLD_KEYS = (
    "threshold",
    "thresholdAmount",
    "minAmount",
    "fullAmount",
    "conditionAmount",
    "reachAmount",
    "orderAmount",
    "startAmount",
)
_REDUCTION_KEYS = (
    "reduction",
    "reductionAmount",
    "discountAmount",
    "reduceAmount",
    "offAmount",
    "minus",
)
_RATE_KEYS = ("discountRate", "rate", "percent", "discountPercent", "rebate")


@dataclass(frozen=True)
class Line:
    code: str
    name: str
    role: str
    qty: int
    unit_fen: int

    @property
    def subtotal_fen(self) -> int:
        return self.qty * self.unit_fen


@dataclass(frozen=True)
class Ladder:
    threshold_fen: int
    reduction_fen: int = 0
    pay_ratio: Decimal | None = None


@dataclass(frozen=True)
class Promotion:
    promo_id: str
    kind: str
    ladders: tuple[Ladder, ...]
    include: frozenset[str] | None = None
    exclude: frozenset[str] = field(default_factory=frozenset)

    def label_for(self, eligible_fen: int) -> tuple[int, str]:
        best = 0
        label = ""
        for ladder in self.ladders:
            if eligible_fen < ladder.threshold_fen:
                continue
            if self.kind == "rate" and ladder.pay_ratio is not None:
                pay = _money_round(Decimal(eligible_fen) * ladder.pay_ratio)
                cut = max(0, eligible_fen - pay)
                text = _fold_text(ladder.pay_ratio)
            else:
                cut = min(eligible_fen, max(0, ladder.reduction_fen))
                text = f"满{_yuan(ladder.threshold_fen)}减{_yuan(ladder.reduction_fen)}"
            if cut > best:
                best = cut
                label = text
        return best, label


@dataclass(frozen=True)
class Discount:
    promo_id: str
    amount_fen: int
    label: str


def extract_promotions(payload: Any) -> list[Promotion]:
    found: list[Promotion] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if _looks_like_promo(node):
                promo = parse_promotion(node)
                if promo is not None:
                    found.append(promo)
                return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return found


def parse_promotion(raw: dict[str, Any]) -> Promotion | None:
    detail = raw.get("ruleDetail", raw.get("rule"))
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = None
    if not isinstance(detail, dict):
        detail = raw
    unit = raw.get("unit") or detail.get("unit")
    unit_text = str(unit) if unit is not None else None
    ladders = _ladders_from(detail, unit_text)
    if not ladders:
        return None
    include, exclude = _scope(raw.get("products"))
    kind = _kind(raw, ladders)
    promo_id = str(raw.get("promotionId") or raw.get("id") or kind)
    return Promotion(
        promo_id=promo_id,
        kind=kind,
        ladders=tuple(ladders),
        include=include,
        exclude=exclude,
    )


def apply_best(lines: list[Line], promotions: list[Promotion]) -> Discount:
    food = sum(line.subtotal_fen for line in lines)
    best = Discount(promo_id="", amount_fen=0, label="未命中满减")
    for promo in promotions:
        eligible = _eligible(lines, promo)
        amount, label = promo.label_for(eligible)
        amount = min(amount, food)
        if amount > best.amount_fen or (amount == best.amount_fen and amount and promo.promo_id < best.promo_id):
            if amount <= 0:
                continue
            best = Discount(promo_id=promo.promo_id, amount_fen=amount, label=label or "已命中优惠")
    return best


def _eligible(lines: list[Line], promo: Promotion) -> int:
    total = 0
    for line in lines:
        if promo.include is not None and line.code not in promo.include:
            continue
        if line.code in promo.exclude:
            continue
        total += line.subtotal_fen
    return total


def _looks_like_promo(node: dict[str, Any]) -> bool:
    return any(key in node for key in ("promotionType", "ruleDetail", "promotionId", "ruleCategory"))


def _kind(raw: dict[str, Any], ladders: list[Ladder]) -> str:
    promo_type = _as_int(raw.get("promotionType"))
    category = _as_int(raw.get("ruleCategory"))
    if promo_type == 33 or category == 30:
        return "rate"
    if promo_type == 31 or category == 40:
        return "off"
    if any(ladder.pay_ratio is not None for ladder in ladders) and all(
        ladder.reduction_fen == 0 for ladder in ladders
    ):
        return "rate"
    return "off"


def _ladders_from(node: Any, unit: str | None) -> list[Ladder]:
    found: list[Ladder] = []

    def visit(current: Any) -> None:
        if isinstance(current, dict):
            ladder = _ladder_from_mapping(current, unit)
            if ladder is not None:
                found.append(ladder)
                return
            for value in current.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(current, list):
            for value in current:
                visit(value)

    visit(node)
    return found


def _ladder_from_mapping(node: dict[str, Any], unit: str | None) -> Ladder | None:
    threshold = _first_number(node, _THRESHOLD_KEYS)
    reduction = _first_number(node, _REDUCTION_KEYS)
    rate = _first_number(node, _RATE_KEYS)
    if rate is None and "discount" in node:
        raw_discount = _number(node.get("discount"))
        if raw_discount is not None and raw_discount <= 1:
            rate = raw_discount
        elif reduction is None:
            reduction = raw_discount
    if threshold is None or (reduction is None and rate is None):
        return None
    threshold_fen = money_to_fen(threshold, unit)
    if threshold_fen is None:
        return None
    reduction_fen = 0
    if reduction is not None:
        reduction_fen = money_to_fen(reduction, unit) or 0
    return Ladder(
        threshold_fen=threshold_fen,
        reduction_fen=reduction_fen,
        pay_ratio=_pay_ratio(rate),
    )


def _scope(products: Any) -> tuple[frozenset[str] | None, frozenset[str]]:
    if products is None:
        return None, frozenset()
    items = products if isinstance(products, list) else [products]
    include: set[str] = set()
    exclude: set[str] = set()
    saw_all = False
    saw_include = False
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type", 3)
        codes = _codes(item)
        if kind in (3, "3", "all", "ALL"):
            saw_all = True
        elif kind in (1, "1", "include"):
            saw_include = True
            include.update(codes)
        elif kind in (2, "2", "exclude"):
            exclude.update(codes)
    if saw_include and not saw_all:
        return frozenset(include), frozenset(exclude)
    return None, frozenset(exclude)


def _codes(node: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key in ("productCode", "productCodes", "code", "codes"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            codes.add(value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    codes.add(item.strip())
                elif isinstance(item, dict):
                    codes.update(_codes(item))
    nested = node.get("products") or node.get("productList")
    if isinstance(nested, list):
        for item in nested:
            if isinstance(item, dict):
                codes.update(_codes(item))
    return codes


def _pay_ratio(value: float | None) -> Decimal | None:
    if value is None or value <= 0:
        return None
    number = Decimal(str(value))
    if number <= 1:
        return number
    if number <= 10:
        return number / Decimal(10)
    if number <= 100:
        return number / Decimal(100)
    return None


def _fold_text(ratio: Decimal) -> str:
    fold = ratio * Decimal(10)
    text = format(fold, "f").rstrip("0").rstrip(".")
    return f"{text}折"


def _first_number(node: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in node:
            number = _number(node.get(key))
            if number is not None:
                return number
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number)


def _money_round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _yuan(fen: int) -> str:
    sign = "-" if fen < 0 else ""
    fen = abs(int(fen))
    if fen % 100 == 0:
        return f"{sign}{fen // 100}"
    return f"{sign}{fen // 100}.{fen % 100:02d}"
