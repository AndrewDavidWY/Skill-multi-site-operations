# 多站点运营数据整合与每日更新

**Multi-site Operations · `multi-site-operations`**

建立多站点 GA4 数据契约、最小读取权限、人工与自动对账、日报和时效检查。真实零值、未取得、报告处理延迟和缓存过期分别显示。

## 使用

将 [`multi-site-operations/`](multi-site-operations/) 完整放入支持 Agent Skills 的工具的技能目录。例如 Codex 通常使用 `~/.codex/skills/`。

> 使用 $multi-site-operations，为这些站点整理 GA4 property 映射和指标口径，先完成一次可核查日报，再列出每日自动更新所需的最小授权。

## 内容

- [技能入口](multi-site-operations/SKILL.md)、[数据契约](multi-site-operations/references/data-contract.md)、[访问与自动化](multi-site-operations/references/access-and-automation.md)。
- [虚构站点配置](multi-site-operations/assets/sites.example.json)、[合成快照](multi-site-operations/assets/snapshots.example.json)、[日报模板](multi-site-operations/assets/daily-update.md)。
- [离线检查器](multi-site-operations/scripts/check_daily_snapshot.py) 与合成测试。Python 3.10+，标准库；系统需要 IANA 时区数据。

```bash
python3 multi-site-operations/scripts/check_daily_snapshot.py multi-site-operations/assets/sites.example.json multi-site-operations/assets/snapshots.example.json --report-date 2026-01-12 --as-of 2026-01-15T12:00:00Z
python3 -m unittest discover -s multi-site-operations/scripts -p 'test_*.py'
```

检查器要求并保留 `data_mode=demo` 或 `real_snapshot`，来源声明不代表已经验真；它不联网、不配置 Google 身份、不创建定时任务。它验证已有归一化快照的结构、映射、数值和时效；不能证明真实站点测量正确。自动读取和发送仍需任务范围内的授权与真实运行验证。输出含站点标识和自由文本错误原因，仅供受控核验；公开看板须另按用户批准的字段白名单投影，不能直接发布完整检查结果。

所有 property ID、站点和数据均为虚构。公有仓库不包含真实业务指标、客户身份或凭据。接口与角色说明链接到 Google 官方文档，使用时应复核当前版本。
