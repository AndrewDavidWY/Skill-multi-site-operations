# GA4 数据契约与离线快照

## 每个站点确认什么

站点 ID 是稳定内部键；主机名列表用于已验证的站点边界；property ID 用于 Data API；measurement ID 用于采集配置，二者不互换。主机过滤不能自然解决跨域用户、会话和重复采集问题，需要单独核实共享 property 的测量设计。

固定指标列表、`date` 粒度、property 时区、过滤器、查询日期、访问限制和定义版本。示例只用 activeUsers、sessions、screenPageViews、engagementRate，不声称它们能相加得到跨站去重总量。需要自定义事件时先核实注册、兼容性与定义。

## 配置文件

`sites.example.json` 使用虚构站点与数字 property ID。每站字段：

- `site_id`、`label`、`property_id`、`hostnames`、`timezone`。
- `metrics`：API 指标列表；`dimensions` 固定为 `["date"]`。
- `max_fetch_age_hours`：报告允许的取数年龄，用户可调整。
- `settling_hours`：从数据日结束后预留的处理窗口，不是 Google SLA，也不能证明窗口外数据不会修订。

## 归一化快照

顶层 `data_mode` 必须明确为 `demo`（合成演示）或 `real_snapshot`（声明来自真实采集的快照）。这只是来源声明，检查器不证明其真实性，也不支持把快照标为实时数据。输出原样保留该模式；缺失或其他值会拒绝。

每行代表某站点某一天，唯一键 `(site_id, report_date)`；重新采集同一天应版本化保存，检查输入中仅提供选定版本，不盲目累加。

- `status`：`ok`、`error`、`not_connected`。失败记录无指标值，单列 `error_reason` 和 `attempted_at`（尝试时间），不伪造成功取数时间。
- `method`：`manual_export` 或 `data_api`，不会因为填了 `data_api` 就证明真实请求成功。
- `fetched_at`：真实取数时刻，必须带时区；不能更新成报告生成时间。
- `query`：property、主机名、时区、指标与维度；需与契约完全一致。
- `values`：数值或 null。缺失不填零；样例验证器的 engagementRate 使用 0–1。
- `pagination_complete`、`quality_metadata_available`：真实是否完成/可获得，未知写 null。
- `quality`：保留抽样、阈值、other-row、截断、指标限制与空原因。来自 API 原始 metadata 的转换需留存原始结果以追溯；手工导出不知道的项不能编造。

离线脚本返回每站值、问题列表和当前状态。`ready` 只表示此配置下没有检测到机械性缺口，不代表测量实施、业务真实性或已最终结算。`provisional` 表示取数时仍在处理窗口；即使当前时间已超出窗口，早期快照也必须重新采集才能解除该标记。`stale` 表示取数过旧，`quality_limited` 表示口径/质量限制，`missing` 和 `error` 保留缺失。多种问题同时显示在 flags 中。

## 受控核验与公开投影

离线检查结果用于受控核验，不是已脱敏的公开导出；站点 ID、`method` 和 `error_reason` 等字段可能包含内部信息或原始错误文本。不要把完整输出直接提交到公共目录或公开接口。

需要公开看板时，根据用户批准的数据范围另建封闭的字段白名单，只投影获准的汇总指标与必要说明；原始请求／响应、身份、凭据、错误堆栈和未批准字段不进入公开产物。保留 `data_mode`、数据日、原取数时间及缺失／质量／过期标记，不能用报告生成时间把旧快照伪装成实时值。检查器不验证公开授权或执行这一步投影。

## 可比性与总量

用户指标一般不可按天或按站相加去重；比例不直接取平均；共享 property 的不同主机可能包含同一用户或会话。不同采集、consent、身份识别、时区、渠道规则、过滤器、币种和采样条件应先对齐。不能从各站 KPI 简单求和声称“全网独立用户”。

官方依据：[指标与维度](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)、[runReport](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport)、[响应元数据](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/ResponseMetaData)、[数据新鲜度](https://support.google.com/analytics/answer/11198161)。执行时核实当前 API 字段，不把此示例当作 Google 的官方接口格式。
