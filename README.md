# 团餐操盘手

12 个人、人均 35 元、送到公司。按这家店**现在**的企业团餐满减，给出三套能 AA 的方案。确认之前不下单。

这是麦当劳开发者创新挑战的参赛作品，不是麦当劳官方产品。规则和报名说明在 [mcd-developer-innovation-challenge](https://github.com/M-China/mcd-developer-innovation-challenge)。

## 演示

下面这组数字来自 `fixtures/store.json`，菜单和满减都是假的，只用来看形状。真点餐会换成门店的 `query-meals` 和 `query-promotions`。

12 人，人均预算 35 元，合计 420 元。

| 方案 | 搭配 | 满减 | 实付 | 人均 |
| --- | --- | --- | ---: | ---: |
| A 省钱 | 麦辣鸡腿堡 + 玉米杯 + 中可乐 | 满 300 减 60 | 312.00 | 26.00 |
| B 均衡 | 麦辣鸡腿堡 + 中薯条 + 中可乐 | 满 300 减 60 | 372.00 | 31.00 |
| C 热闹 | 板烧鸡腿堡 + 玉米杯 + 热美式 | 满 480 减 120 | 420.00 | 35.00 |

打开 [examples/demo-card.html](examples/demo-card.html) 可以看三张卡片。完整文本在 [examples/demo-report.md](examples/demo-report.md)。

## 它做什么

企业团餐（`beType=6`）才有满减满折和助餐服务。个人点餐的省钱脚本用不上这条链路。

1. 查地址和可配送门店。
2. 读菜单、促销、助餐服务。
3. 在人均预算里出省钱、均衡、热闹三套，默认每人同款。
4. 用 `calculate-price` 覆盖本地估算。价格单位是分，展示时换成元。
5. 你说「下单 A」之后才 `create-order`。

名称里带「套餐」或「全餐」的，不会再加一份小食和饮料。多条促销不叠加，只留优惠更大的一条。

## 本地跑

需要 Python 3.10 或以上。不装第三方包。

```powershell
cd D:\dev\mcd-office-lunch
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
python -m mcd_office_lunch --people 12 --budget 35
```

接上自己的 MCP Token 以后，按真实地址出方案：

```powershell
$env:MCD_MCP_TOKEN = "你的令牌"
python -m mcd_office_lunch --people 12 --budget 35 --address-id 地址ID --avoid 可乐
```

多家门店时，命令会列出 `storeCode` 和 `beCode`，你选定后再加 `--store` 和 `--be-code`。核对实付加 `--verify`。

下单必须两道闸都在：

```powershell
python -m mcd_office_lunch --people 12 --budget 35 --address-id 地址ID --store 门店码 --be-code 业务码 --service 助餐码 --place A --yes
```

没有 `--yes` 不会创建订单。Token 不要写进仓库。

配置示例见 `mcp-config.example.json`。工具参数和满减字段见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。给 Agent 用的流程在 [SKILL.md](SKILL.md)，安装副本在 `skill/mcd-office-lunch/`。

## 报名

仓库保持公开，根目录保留这些文件：

- `README.md`
- `CONTEST_DECLARATION.md`（官方模板原文，没有改过一个字）
- `MCP_INTEGRATION.md`
- `SKILL.md` 和 `src/`

然后按活动仓库的说明开一个 Issue，附上你的仓库地址。同一个账号只认星数最高的那个仓库。报名截止和定榜时间以活动 README 为准，当前写的是 2026-10-25 23:59 截止，2026-10-26 00:00 定榜。
