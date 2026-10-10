"""Meal catalog normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_DRINKS = (
    "可乐",
    "雪碧",
    "茶",
    "咖啡",
    "汁",
    "乳",
    "饮",
    "美式",
    "拿铁",
    "奶昔",
    "汽水",
    "矿泉水",
    "优品",
    "奶茶",
)
_SIDES = ("薯", "玉米", "派", "麦乐鸡", "鸡块", "鸡翅", "小食", "沙拉", "甜筒", "圣代", "鸡米花")
_MAINS = ("堡", "卷", "饭", "粥", "蛋", "牛", "猪柳", "麦香", "板烧", "鸡腿", "套餐", "全餐", "麦辣")

_CODE_KEYS = ("productCode", "product_code", "skuCode")
_NAME_KEYS = ("productName", "name", "showName", "title", "shortName")
_FEN_KEYS = ("priceFen", "price_fen", "amountFen", "salePriceFen")
_MONEY_KEYS = ("price", "salePrice", "amount", "productPrice", "saleAmount")


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    price_fen: int
    role: str


def classify(name: str) -> str:
    if "套餐" in name or "全餐" in name:
        return "main"
    if any(word in name for word in _DRINKS):
        return "drink"
    if any(word in name for word in _SIDES):
        return "side"
    if any(word in name for word in _MAINS):
        return "main"
    return "other"


def money_to_fen(value: Any, unit: str | None = None) -> int | None:
    """Convert a menu or rule amount to fen.

    Explicit unit wins. In auto mode, decimals and numbers below 1000 are yuan,
    and integers at or above 1000 are fen. Menu prices should pass unit="fen".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text) if "." in text else int(text)
        except ValueError:
            return None
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    if number <= 0:
        return None
    hint = (unit or "").lower()
    if hint in {"fen", "cent", "分"}:
        return int(round(number))
    if hint in {"yuan", "元"}:
        return int(round(number * 100))
    if isinstance(number, float) and not float(number).is_integer():
        return int(round(number * 100))
    whole = int(round(number))
    if whole >= 1000:
        return whole
    return whole * 100


def extract_products(payload: Any, *, price_unit: str = "fen") -> list[Product]:
    found: dict[str, Product] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            product = _product_from(node, price_unit)
            if product is not None:
                found.setdefault(product.code, product)
                return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return sorted(found.values(), key=lambda item: (item.role, item.price_fen, item.code))


def _product_from(node: dict[str, Any], price_unit: str) -> Product | None:
    code = _first_text(node, _CODE_KEYS)
    if not code:
        code = _first_text(node, ("code",))
    name = _first_text(node, _NAME_KEYS)
    if not code or not name:
        return None
    price = None
    for key in _FEN_KEYS:
        if key in node:
            price = money_to_fen(node.get(key), "fen")
            break
    if price is None:
        declared = node.get("priceUnit") or node.get("unit") or price_unit
        for key in _MONEY_KEYS:
            if key in node:
                price = money_to_fen(node.get(key), str(declared))
                break
    if price is None:
        return None
    return Product(code=str(code), name=str(name), price_fen=price, role=classify(str(name)))


def _first_text(node: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = node.get(key)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if text:
            return text
    return None
