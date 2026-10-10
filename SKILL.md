---
name: mcd-office-lunch
description: 企业团餐操盘手。按人数、人均预算、忌口和配送地址，读取麦当劳企业团餐的菜单、满减满折和助餐服务，给出省钱、均衡、热闹三套方案和人均 AA。用户明确确认前不下单。
---

# 团餐操盘手

只做企业团餐：`beType=6`，`orderType=2`。到店自取、得来速、普通麦乐送不要走这里。

人数乘以人均预算是硬上限。超了就换方案，不要默默超支。

## 先问清楚

缺什么问什么，不要猜：

- 几个人
- 人均预算，单位元
- 用哪一个已有地址；没有就问城市、联系人、手机号、地址和门牌
- 忌口，例如「不要可乐」
- 要不要餐具

## 工具顺序

1. `delivery-query-addresses`。没有可用地址时，再 `delivery-create-address`。不要把手机号写进仓库。
2. `delivery-query-stores`，`addressId` 用上一步的地址，`beType=6`。多家店就列出来让用户选。记下 `storeCode` 和 `beCode`。
3. 同一家店各调一次：
   - `query-meals`：`storeCode`，`orderType=2`，`beType=6`，`beCode`
   - `query-promotions`：同样四个字段
   - `query-meal-assistance`：`storeCode`，`orderType=2`，`beType=6`，`beCode`
4. 把三份 JSON 存下来，用方案引擎出三套。不要心算满减。

```powershell
$env:PYTHONPATH = "src"
python -m mcd_office_lunch --people 12 --budget 35 --avoid 可乐 --meals meals.json --promotions promos.json --assistance assist.json
```

5. 助餐服务让用户选一个 `gmServiceCode`。没选就只展示，不默认收费服务。
6. 三套都调 `calculate-price`（`orderType=2`，`beType=6`，`beCode`，`gmServiceCode`，`items`）。接口返回的实付覆盖本地估算。本地满减只用来解释为什么便宜。价格字段单位是分，展示前除以 100。
7. 输出方案 A 省钱、方案 B 均衡、方案 C 热闹。然后停。

## 下单

只有用户明确说「下单 A」或「下单 B」「下单 C」时，才调 `create-order`。

- `orderType=2`
- `beType=6`
- `addressId`、`storeCode`、`beCode`、`gmServiceCode` 都要有
- `items` 用该方案的 `productCode` 和数量
- `remark` 最多 50 字

命令行对应：

```powershell
python -m mcd_office_lunch --people 12 --budget 35 --address-id 地址ID --store 门店码 --be-code 业务码 --service 助餐码 --place A --yes
```

没有 `--yes` 不会下单。

## 方案怎么选

- 省钱：每人同款。能凑齐主食、小食、饮料时，取得实付最低的一档。
- 均衡：三样凑齐，总价靠近预算，但留一点余量。
- 热闹：仍在预算内，把主食和小食往上换。
- 名称里带「套餐」或「全餐」的，不再额外加小食和饮料。
- 多条促销只取优惠更大的一条，不叠加。
- 满减门槛只算规则覆盖的餐品。饮品不在范围内时，不拿它凑门槛。
- 每一类餐品最多比较 12 个：最便宜的 8 个，加上最贵的 4 个。

## 不要做的事

- 不要拿麦当劳和其他品牌比价。
- 不要把 `fixtures/store.json` 里的满减写成全国统一规则。
- 菜单或规则缺价格时就说明缺了什么，不要编。
- 用户没点头之前，禁止 `create-order`。
