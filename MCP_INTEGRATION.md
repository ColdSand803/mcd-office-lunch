# MCP 集成说明

团餐操盘手只走麦当劳官方 MCP 的企业团餐链路。端点是 `https://mcp.mcd.cn`。Token 放在环境变量 `MCD_MCP_TOKEN`，或按 `mcp-config.example.json` 配到客户端。不要把 Token 提交进仓库。

客户端如果要求传输类型，加上 `"type": "streamable-http"`。

## 调用顺序

| 顺序 | 工具 | 关键参数 | 拿来做什么 |
| --- | --- | --- | --- |
| 1 | `delivery-query-addresses` | 无 | 选配送地址，得到 `addressId` |
| 2 | `delivery-create-address` | 城市、联系人、手机号、地址、门牌 | 没有地址时才创建 |
| 3 | `delivery-query-stores` | `addressId`，`beType=6` | 得到 `storeCode` 和 `beCode` |
| 4 | `query-meals` | `storeCode`，`orderType=2`，`beType=6`，`beCode` | 菜单和价格 |
| 4 | `query-promotions` | 同上 | 当前门店满减、满折 |
| 4 | `query-meal-assistance` | `storeCode`，`orderType=2`，`beType=6`，`beCode` | 助餐服务和 `gmServiceCode` |
| 5 | `calculate-price` | 上面的门店字段、`gmServiceCode`、`items` | 用接口实付覆盖本地估算 |
| 6 | `create-order` | 再加 `addressId` | 只在用户确认方案后调用 |

`orderType=2` 表示外送。企业团餐必须同时是 `beType=6`。到店不传这组参数。

## 金额

`calculate-price` 的金额字段单位是分。展示时除以 100。

菜单里的价格优先读 `priceFen`、`amountFen`、`salePriceFen`。没有这些字段时，默认把 `price` 也当成「分」。如果某份离线 JSON 写的是元，运行时加 `--price-unit yuan`。

## 促销

`query-promotions` 返回的原始规则里，本仓库识别这些字段：

- `promotionType`：`31` 满额减，`33` 订单折扣
- `ruleCategory`：`40` 满减，`30` 折扣
- `products.type`：`1` 只含列出的 `productCode`，`2` 排除，`3` 全部
- `ruleDetail`：门槛和优惠。支持 `threshold`、`thresholdAmount`、`minAmount`，以及 `reduction`、`discountAmount`。折扣支持 `discountRate`、`rate`，`88` 和 `0.88` 都按 88 折。
- `ruleDetail.unit`：`yuan` 或 `fen`。没写时，小于 1000 的整数按元，大于等于 1000 的按分。

多条规则不叠加，只保留当前购物车优惠金额更大的一条。阶梯满减取已经达到、且减免更多的那一档。

助餐服务费加在优惠之后，不拿去凑满减门槛。

## 本地引擎

实时结果可以整包存成 JSON，再交给：

```powershell
python -m mcd_office_lunch --people 12 --budget 35 --meals meals.json --promotions promos.json --assistance assist.json --service PICKUP
```

`--verify` 会再调 `calculate-price`。`--place A --yes` 才会 `create-order`。

没有 Token 时，用 `fixtures/store.json` 看方案形状。那份菜单和满减是演示数据，不是门店实时价。
