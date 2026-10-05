# Call Atlas · 征稿雷达

面向 AI、NLP、可解释 AI、教育技术、教育学、心理学、STEM 与语言教育的专题征稿工作台。

**网站：https://wdeliang978.github.io/special-issue-radar/**

## 使用

- 按研究方向、出版社、SSCI / SCIE、摘要与全文截止日期筛选；支持搜索、浏览器本地收藏和 ICS 日历导出。
- **GitHub 通知**：在本仓库选择 **Watch → Custom → Issues**。检查程序会为已核验的新征稿、截止日期变更及临近截止生成每日汇总 Issue，并提醒仓库所有者。邮件送达取决于个人 GitHub 通知设置。
- **RSS**：订阅 `https://wdeliang978.github.io/special-issue-radar/feed.xml`。首次订阅会读取当前符合条件的清单；RSS 阅读器通常以稳定 GUID 判断新条目。
- 自动任务每天 **13:17 UTC** 运行（纽约夏令时 09:17，冬令时 08:17），也可在 Actions 手动运行。

## 数据口径与覆盖边界

仅通过具体期刊的官方收录说明确认 SSCI / SCIE。SCI 在此按 SCIE 口径处理。**ESCI、Scopus、有影响因子不等于 SSCI / SCIE。** 不公开本地原始工作簿，只发布本次核验的事实字段、简短摘要和官方来源。

`journals.json` 保存已核验期刊名录。`sources.json` 保存官方出版社入口与期刊入口。采集程序读取这些入口发现新专题，只有期刊身份唯一、索引核验有效、方向相关、投稿日期明确的记录自动进入正式清单。其余发现写入 `review-queue.json`，不会向用户推送。新增期刊需要有明确官方索引证据后加入名录。

这是基于配置来源的持续监测系统，**不保证全网、所有出版社及所有 SSCI / SCIE 期刊零遗漏**。部分出版社使用动态页面、PDF、登录或反爬措施；无法读取时显示来源失败并保留最近证据，不会当作零条征稿。支持直接托管在官方域名的文本 PDF；ET&S 等官网的外链 PDF 会进入发现与待核验流程，不能自动读取的文档仍需人工核验。不会绕过网站访问限制。来源页面 7 天未成功复核则暂停通知，索引证据 90 天未成功复核则退出展示与推送。

摘要阶段和全文阶段单独保存。强制摘要或要求未明示的摘要阶段已截止时，不作为仍可新投稿推荐；可选摘要已截止不影响全文阶段。未公布摘要日期不表示免交摘要。日期未提供时区时，本站不擅自推定具体截止时刻，日历输出为全天事件。发现日期不等于出版社发布日。

初始数据于 2026-10-04 查阅官方页面。后续页面变更可能需要补充人工核验。投稿前应打开原始征稿核对资格、稿件类型和提交要求。

## 维护

网站是无构建依赖的 HTML / CSS / JavaScript。采集器使用 Python 3.12 与 pypdf 解析文本 PDF；无需第三方密钥。GitHub Actions 使用本仓库自动提供的临时 `GITHUB_TOKEN`，不把凭据写入代码或网页。

```text
python -m pip install -r requirements.txt
python -m http.server 8765
node --test rules.test.js
python -m unittest test_collector.py
python collector.py --offline
python collector.py
```

工作流已包含测试、官方来源检查、通知去重、保存数据与 GitHub Pages 发布。Pages 的 Source 应设为 **GitHub Actions**。通知失败时工作流明确失败；成功发出的 Issue 含事件标记，下次运行可恢复送达记录，避免同一事件重复推送。

GitHub 定时任务可能延迟，长期无活动的公共仓库定时任务可能被平台停用。可在 Actions 查看运行结果、失败原因及手动恢复。参见 [GitHub 官方定时任务说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

关键文件：`data.json`（展示数据）、`journals.json`（索引依据）、`sources.json`（来源入口）、`collector.py`（检查与通知）、`notification-state.json`（送达记录）、`feed.xml`（RSS）。

## 2026-10-05 覆盖修正

名录扩至 19 本，加入 Distance Education、Educational Technology & Society 和 Learning and Individual Differences。新增四条开放征稿，保留一条已截止的 LID 征稿用于查询。前台「来源与核验」列出全部期刊、记录数、入口和正文读取情况。该名录是实际监测范围，不代表这些领域的全部 SSCI / SCIE 期刊。

发现器现在识别独立期刊入口、官方 PDF 链接，并使用期刊列表中的专题标题识别 ScienceDirect 的 h3 专题标题，避免误用 h1 期刊名称。PDF 时间表中的返修、终稿与出版日不会被当作首次全文截止。外部文档只在已配置期刊官网明确链接时进入候选，不能借此扩大索引准入。
