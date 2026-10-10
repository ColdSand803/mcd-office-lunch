import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_office_lunch.catalog import extract_products, money_to_fen
from mcd_office_lunch.planner import plan_group_meal, split_even
from mcd_office_lunch.promotions import Line, apply_best, extract_promotions

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "fixtures" / "store.json").read_text(encoding="utf-8"))


class CatalogTests(unittest.TestCase):
    def test_nested_menu_uses_fen_fields(self) -> None:
        products = extract_products(FIXTURE["meals"])
        codes = {item.code: item for item in products}
        self.assertEqual(codes["1001"].price_fen, 1600)
        self.assertEqual(codes["1001"].role, "main")
        self.assertEqual(codes["2002"].role, "side")
        self.assertEqual(codes["3002"].role, "drink")

    def test_money_units(self) -> None:
        self.assertEqual(money_to_fen(18, "yuan"), 1800)
        self.assertEqual(money_to_fen(800, "fen"), 800)
        self.assertEqual(money_to_fen("18.5", "yuan"), 1850)
        self.assertIsNone(money_to_fen(0, "fen"))


class PromotionTests(unittest.TestCase):
    def test_demo_ladder_picks_the_deeper_cut(self) -> None:
        rules = extract_promotions(FIXTURE["promotions"])
        lines = [Line("1003", "板烧鸡腿堡", "main", 12, 2700), Line("2001", "玉米杯", "side", 12, 700), Line("3002", "热美式", "drink", 12, 1100)]
        discount = apply_best(lines, rules)
        self.assertEqual(discount.amount_fen, 12000)
        self.assertEqual(discount.label, "满480减120")

    def test_include_scope_ignores_drinks(self) -> None:
        payload = {
            "promotionId": "mains",
            "promotionType": 31,
            "products": {"type": 1, "productCode": ["1001"]},
            "ruleDetail": {"unit": "yuan", "threshold": 50, "reduction": 10},
        }
        rules = extract_promotions(payload)
        lines = [Line("1001", "麦辣鸡腿堡", "main", 1, 10000), Line("3001", "中可乐", "drink", 1, 5000)]
        discount = apply_best(lines, rules)
        self.assertEqual(discount.amount_fen, 1000)

    def test_rate_and_best_of_two_promos(self) -> None:
        payload = [
            {
                "promotionId": "b",
                "promotionType": 33,
                "products": {"type": 3},
                "ruleDetail": {"unit": "yuan", "threshold": 50, "discountRate": 88},
            },
            {
                "promotionId": "a",
                "promotionType": 31,
                "products": {"type": 3},
                "ruleDetail": {"unit": "yuan", "threshold": 50, "reduction": 30},
            },
        ]
        lines = [Line("1001", "麦辣鸡腿堡", "main", 1, 10000)]
        discount = apply_best(lines, extract_promotions(payload))
        self.assertEqual(discount.promo_id, "a")
        self.assertEqual(discount.amount_fen, 3000)


class PlannerTests(unittest.TestCase):
    def test_three_plans_for_twelve_people(self) -> None:
        planned = plan_group_meal(
            FIXTURE["meals"],
            FIXTURE["promotions"],
            FIXTURE["assistance"],
            people=12,
            budget_yuan=35,
            service_code="ROOM",
        )
        save, balance, lively = planned.plans
        self.assertEqual([line.code for line in save.lines], ["1001", "2001", "3001"])
        self.assertEqual(save.payable_fen, 31200)
        self.assertEqual([line.code for line in balance.lines], ["1001", "2002", "3001"])
        self.assertEqual(balance.payable_fen, 37200)
        self.assertEqual([line.code for line in lively.lines], ["1003", "2001", "3002"])
        self.assertEqual(lively.payable_fen, 42000)
        self.assertTrue(all(plan.within_budget for plan in planned.plans))
        self.assertEqual(planned.assistance_name, "配送入室")

    def test_avoid_cola_and_even_split(self) -> None:
        planned = plan_group_meal(
            FIXTURE["meals"],
            FIXTURE["promotions"],
            people=12,
            budget_yuan=35,
            avoid=["可乐"],
        )
        codes = [line.code for line in planned.plans[0].lines]
        self.assertNotIn("3001", codes)
        self.assertEqual(planned.plans[0].payable_fen, 34800)
        shares = split_even(100, 3, ["甲", "乙", "丙"])
        self.assertEqual([share.fen for share in shares], [34, 33, 33])
        self.assertEqual(sum(share.fen for share in shares), 100)

    def test_budget_too_small_is_marked(self) -> None:
        planned = plan_group_meal(FIXTURE["meals"], FIXTURE["promotions"], people=12, budget_yuan=10)
        self.assertFalse(planned.plans[0].within_budget)

    def test_bad_headcount(self) -> None:
        with self.assertRaises(ValueError):
            plan_group_meal(FIXTURE["meals"], people=0, budget_yuan=35)

    def test_combo_does_not_add_extra_side_and_drink(self) -> None:
        meals = {
            "menu": [
                {"productCode": "9001", "productName": "巨无霸套餐", "priceFen": 3900},
                {"productCode": "2002", "productName": "中薯条", "priceFen": 1200},
                {"productCode": "3001", "productName": "中可乐", "priceFen": 800},
            ]
        }
        planned = plan_group_meal(meals, people=2, budget_yuan=50)
        self.assertEqual([line.code for line in planned.plans[0].lines], ["9001"])


if __name__ == "__main__":
    unittest.main()
