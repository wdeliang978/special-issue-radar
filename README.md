# Call Atlas · 征稿雷达

面向 AI、NLP、可解释 AI、教育技术、教育学、心理学、STEM 与语言教育的专题征稿工作台。

**网站：https://wdeliang978.github.io/special-issue-radar/**

## 使用

- 按研究方向、出版社、SSCI / SCIE、摘要与全文截止日期筛选；支持搜索、浏览器本地收藏和 ICS 日历导出。
- **GitHub 通知**：在本仓库选择 **Watch → Custom → Issues**。每周检查发现新征稿、截止日期变更及临近截止时生成汇总 Issue，并提醒仓库所有者；无变化不发通知。邮件送达取决于个人 GitHub 通知设置。
- **RSS**：订阅 `https://wdeliang978.github.io/special-issue-radar/feed.xml`。首次订阅会读取当前符合条件的清单；RSS 阅读器通常以稳定 GUID 判断新条目。
- 自动任务每周一 **13:17 UTC** 运行（纽约夏令时 09:17，冬令时 08:17），也可在 Actions 手动运行。网站发布只重新生成页面，不额外扫描；检查脚本不调用聊天模型，也不消耗聊天 token。

## 数据口径与覆盖边界

收录依据可以是具体期刊的官方索引说明，或用户明确提供的 JCR 清单中的 SSCI / SCIE Edition。两类证据分别标注；附件来源保留文件名、月份、工作表及行号，不声称已完成官网实时核验。SCI 按 SCIE 口径处理。**ESCI、Scopus、有影响因子不等于 SSCI / SCIE。** 不上传原始工作簿、JIF 或引文指标，只发布期刊身份、收录类别和来源引用。

`journals.json` 保存期刊名录及收录依据。`sources.json` 保存出版社入口与期刊入口。采集程序读取这些入口和一层明确链接的征稿栏目，只有期刊身份唯一、索引证据有效、方向相关、投稿日期明确的记录进入正式清单。其余发现写入 `review-queue.json`，不会向用户推送。每次最多检查 400 个候选，按期刊轮转并优先处理尚未检查或上次检查较早的链接；受限来源不会抹掉既有候选。

这是基于配置来源的持续监测系统，**不保证全网、所有出版社及所有 SSCI / SCIE 期刊零遗漏**。部分出版社使用动态页面、PDF、登录或反爬措施；无法读取时显示失败并保留最近证据，不会当作零条征稿。支持官方域名的文本 PDF；ET&S 等官网的受限外链文档保留在候选中，仍需人工核验。不会绕过访问限制。征稿正文超过 8 天未复核则暂停通知（每周检查加一天余量）。官网索引证据有效期 90 天；本次用户 JCR 附件从 2026-06-01 起一年有效，之后需新版清单或官网证据。官网明确降为 ESCI 时立即覆盖旧清单依据，停止展示与通知。

摘要阶段和全文阶段单独保存。强制摘要或要求未明示的摘要阶段已截止时，不作为仍可新投稿推荐；可选摘要已截止不影响全文阶段。未公布摘要日期不表示免交摘要。日期未提供时区时，本站不擅自推定具体截止时刻，日历输出为全天事件。发现日期不等于出版社发布日。

初始数据于 2026-10-04 查阅官方页面。后续页面变更可能需要补充人工核验。投稿前应打开原始征稿核对资格、稿件类型和提交要求。

## 维护

网站是无构建依赖的 HTML / CSS / JavaScript。采集器使用 Python 3.12、pypdf（文本 PDF）与 Protego（网站抓取规则）；无需第三方密钥。GitHub Actions 使用本仓库自动提供的临时 `GITHUB_TOKEN`，不把凭据写入代码或网页。

```text
python -m pip install -r requirements.txt
python -m http.server 8765
node --test rules.test.js
python -m unittest
python collector.py --offline
python collector.py
```

工作流已包含测试、官方来源检查、通知去重、保存数据与 GitHub Pages 发布。Pages 的 Source 应设为 **GitHub Actions**。通知失败时工作流明确失败；成功发出的 Issue 含事件标记，下次运行可恢复送达记录，避免同一事件重复推送。

GitHub 定时任务可能延迟，长期无活动的公共仓库定时任务可能被平台停用。可在 Actions 查看运行结果、失败原因及手动恢复。参见 [GitHub 官方定时任务说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

关键文件：`data.json`（展示数据）、`journals.json`（索引依据）、`sources.json`（来源入口）、`collector.py`（检查与通知）、`notification-state.json`（送达记录）、`feed.xml`（RSS）。

## 2026-10-05 期刊名录扩展

导入用户提供的 `SSCI_JCR_JournalResults_06_2026.xlsx`：教育学 SSCI 256 行、教育学 SCIE 43 行、心理学 SSCI 146 行，共 445 条有效记录，按 ISSN 去重为 **432 本**期刊。10 本已存在，新增 **422 本**，原有 19 本全部保留，总名录 **441 本**。Science Education 和 Science & Education 是不同期刊，分别保留。心理学工作表属于 `PSYCHOLOGY, MULTIDISCIPLINARY`，不代表所有心理学细分类别。

保留原有 AI / NLP 出版社来源和全部征稿，包括 Distance Education、Educational Technology & Society、Learning and Individual Differences。「来源与核验」支持期刊名、出版社、ISSN 搜索、读取状态筛选与分页，区分已登记、入口读取成功、读取受限／身份待核对。收录进名录不等于正在开放征稿。

主页初始定位使用 ISSN 匹配的 OpenAlex 元数据，并对缺失、明显错误和旧平台链接补充官方资料核对。OpenAlex 仅用来定位主页，**不作为 SSCI / SCIE 证据**。旧平台跳转、目录条目错误与访问限制仍可能使部分入口待核对；网页中的成功读取计数只统计当次读到且可识别期刊身份的入口。

发现器现在识别独立期刊入口、官方 PDF 链接，并使用期刊列表中的专题标题识别 ScienceDirect 的 h3 专题标题，避免误用 h1 期刊名称。PDF 时间表中的返修、终稿与出版日不会被当作首次全文截止。外部文档只在已配置期刊官网明确链接时进入候选，不能借此扩大索引准入。

## 2026-10-05 访问与发现修复

本轮实际复查：441 本期刊中，164 本期刊页面可读，129 本由完整读取的官方征稿目录补充，148 本仍受访问限制或征稿入口未接通（此前为 347 本）。原有可读入口全部保留。修正 78 项地址或身份信息，新增 21 条通过核验的征稿；总计 70 条记录，69 条当前开放或预告。以上是本次检查快照，不是永久覆盖保证。

- 正确解压 gzip/deflate，保留普通会话 Cookie，按照重定向后的官方地址解析相对链接；只对临时网关错误或超时有限重试。不会禁用证书验证、解决验证码或伪装浏览器。
- 把 robots.txt 无法读取与明确禁止访问分开，使用 Protego 处理通配符和更具体的允许规则，也兼容没有 Content-Type 的有效规则文件。每个来源保留具体失败原因和最终地址，界面可按原因筛选并展开查看。遵守 Crawl-delay 与 Request-rate。
- Taylor & Francis 使用其 Author Services 页面实际调用的公开 WordPress 接口，分别分页读取 special_issues 和 article_collections；核对总页数、记录数及重复项。任一页失败就显示目录未完整读取。正文同时读取研究范围与投稿说明，额外日期无法判定阶段时进入待核验队列。
- 官方目录状态与期刊页面状态分别显示。期刊产品/信息页可读不等于征稿栏目可读；完整读取出版社目录也不代表所有编辑部公告都已覆盖。仅有目录标题或截止日期的线索不会直接推送。
- 时间表支持日期在标签前面、日期在下一行和括号中的摘要字数；不会把下一行的录用通知、返修或出版日期当作投稿截止。已有人工核对的阶段日期可以由官方接口中未变更的同一日期复核；新增记录仍需明确的投稿阶段证据。
- `source-repairs.json` 记录已核实的迁移地址和身份修复依据。已被无关内容替代的旧域名移出信任列表。收录依据、每周频率与 RSS / GitHub 通知规则保持原有口径。
