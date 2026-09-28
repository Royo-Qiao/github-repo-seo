# GitHub 可发现性分析报告 — Royo-Qiao/Cloudflare-Edgetunnel

> 生成时间: 2026-09-28T07:23:46+00:00 | 认证方式: token | 分析脚本: github-repo-seo skill

## 一、总体评分

**93/100 — Excellent**

| 模块 | 得分 | 权重 | 说明 |
|---|---|---|---|
| 元数据(名称/About/Topics) | 100 | 25% | 仓库 About 区与标签质量 |
| README 结构 | 92 | 30% | 首屏清晰度/安装/截图/badges |
| Topic 质量(覆盖度/精准度) | 100 | 20% | 完全可控:有无 topics、数量、功能词 |
| Topic 预估排名 | 39 | 5% | 半可控 + API 近似值,仅作参考 |
| 生态收录机会 | 90 | 20% | awesome-list 候选 + homepage |

## 二、现状速览

- ⭐ 2 stars / 🍴 1 forks / 👀 0 watchers
- 语言: HTML | 许可: NOASSERTION(有 LICENSE 文件但非标准 SPDX,建议换用常见许可证) | 默认分支: `main`
- 最近推送: 2026-09-28T06:39:23Z | Homepage: —
- 当前描述: 给 cmliu/edgetunnel 套一层本地 Web 向导，一键将 VLESS+WS+TLS 节点部署到 Cloudflare Pages：自动优选 CF IP、生成 Clash 订阅链接、管理后台自托管。Self-hosted GUI for one-click edgetunnel deploy with best-IP selection.
- 当前 Topics(10): clash, cloudflare, cloudflare-pages, cloudflare-workers, edgetunnel, nodejs, proxy, subscription, v2ray, vless
- GitHub 站内搜索位置:
  - 关键词 `Cloudflare Edgetunnel`: 第 9 名 / 共 57 个结果 
  - 关键词 `cf clash`: 第 88 名 / 共 96 个结果 

## 三、问题清单(按严重度)

- **[Info]** (元数据/Metadata) Homepage URL not set.
  - 依据: `homepage` is empty.
  - 修复: Point homepage at docs/demo site if one exists — it renders in the About card.
- **[Info]** (元数据/Metadata) No custom social preview image.
  - 依据: `social_preview_url` is empty.
  - 修复: Upload a social preview (Settings → Social preview) to improve share/link CTR on X/Slack/Google.
- **[Info]** (元数据/Trust) Missing community file: issue_template.
  - 依据: community/profile `files.issue_template` is null.
  - 修复: Add the `issue_template` file (root or .github/).
- **[Info]** (元数据/Trust) Missing community file: security_policy.
  - 依据: community/profile `files.security_policy` is null.
  - 修复: Add the `security_policy` file (root or .github/).
- **[Info]** (README/Proof & Visuals) Static screenshots present but no demo GIF/video.
  - 依据: 1 content image(s), 0 GIFs.
  - 修复: A short demo GIF (or asciinema/YouTube embed) communicates value faster than text.
- **[Info]** (README/Proof & Visuals) Demo images exist but sit under no demo/screenshot section.
  - 依据: No demo-like heading found.
  - 修复: Group visuals under `## Demo` / `## Screenshots` for scannability.
- **[Info]** (README/Badges) No CI/build badge.
  - 依据: Badge URLs: https://img.shields.io/badge/license-MIT-blue.svg, https://img.shields.io/badge/deploys_to-Cloudflare_Pages-f68
  - 修复: Add a GitHub Actions workflow badge to show the build is green.

## 四、Topic 竞争度分析

**Topic 质量分: 100/100**(计入总分,权重 20%)

**Topic 预估排名分: 39/100**(计入总分,权重仅 5%)

> ⚠️ 预估排名是**长期指标**:与 star 数、活跃度强相关,且排名本身是 GitHub Search API(`topic:<name>` 默认 best-match 排序)对 topics 页面排序的近似。**不建议作为短期行动依据** — 短期提分请看「零、优先行动清单」和 Topic 质量分;排名会随 stars 增长自然改善。⭐对比取自 star 排序前 20 名的中位数。

| Topic | 页面内排名 | 收录仓库总数 | Top20 中位⭐ | 你的⭐ | 判定 | 建议 |
|---|---|---|---|---|---|---|
| `clash` | 前N外 | 2509 | 21918 | 2 | 🔴 过卷建议换 | Crowded topic (~2509 repos, top-20 median ≈21918⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `cloudflare` | 前N外 | 10864 | 16335 | 2 | 🔴 过卷建议换 | Crowded topic (~10864 repos, top-20 median ≈16335⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `cloudflare-pages` | 前N外 | 3374 | 1491 | 2 | 🔴 过卷建议换 | Crowded topic (~3374 repos, top-20 median ≈1491⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `cloudflare-workers` | 前N外 | 11416 | 9219 | 2 | 🔴 过卷建议换 | Crowded topic (~11416 repos, top-20 median ≈9219⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `edgetunnel` | ≈#7 | 9 | 3 | 2 | 🟢 强势守住 | Hold position: ranks ~#7 on the topic page — a real traffic source. |
| `nodejs` | 前N外 | 344206 | 96069 | 2 | 🔴 过卷建议换 | Crowded topic (~344206 repos, top-20 median ≈96069⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `proxy` | 前N外 | 16247 | 46931 | 2 | 🔴 过卷建议换 | Crowded topic (~16247 repos, top-20 median ≈46931⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |
| `subscription` | 前N外 | 1413 | 2845 | 2 | 🔴 过卷建议换 | Crowded topic (~1413 repos, top-20 median ≈2845⭐ vs your 2⭐) and the repo is off the visible page — consider swapping for a narrower long-tail topic. |

`clash` best-match 前 5 名示例:
  - clash-verge-rev/clash-verge-rev (147904⭐)
  - chen08209/FlClash (53670⭐)
  - hiddify/hiddify-app (32939⭐)
  - Loyalsoldier/clash-rules (28587⭐)
  - Z-Siqi/Clash-for-Windows_Chinese (28570⭐)

**值得新增的候选 topic**(来自可比仓库的共现统计):
  - `mihomo` — 被 4 个可比仓库使用,如 Z-Siqi/Clash-for-Windows_Chinese, clash-verge-rev/clash-verge-rev
  - `shadowsocks` — 被 4 个可比仓库使用,如 Loyalsoldier/clash-rules, Z-Siqi/Clash-for-Windows_Chinese
  - `clash-meta` — 被 3 个可比仓库使用,如 chen08209/FlClash, clash-verge-rev/clash-verge-rev
  - `windows` — 被 2 个可比仓库使用,如 Z-Siqi/Clash-for-Windows_Chinese, clash-verge-rev/clash-verge-rev
  - `hysteria` — 被 2 个可比仓库使用,如 chen08209/FlClash, hiddify/hiddify-app
  - `hysteria2` — 被 2 个可比仓库使用,如 Z-Siqi/Clash-for-Windows_Chinese, hiddify/hiddify-app
  - `vmess` — 被 2 个可比仓库使用,如 hiddify/hiddify-app, vernesong/OpenClash
  - `ai` — 被 2 个可比仓库使用,如 ClickHouse/ClickHouse, hacksider/Deep-Live-Cam

## 五、Awesome-list 收录机会

检索词: clash, cloudflare, cloudflare-pages, cloudflare-workers, edgetunnel, proxy | 命中 7 个(展示前 5)

- **[anderspitman/awesome-tunneling](https://github.com/anderspitman/awesome-tunneling)** — 21881⭐,最近推送 12 天前,匹配词: cloudflare
  - ℹ️ No CONTRIBUTING file — check the README's 'Contributing' section: https://github.com/anderspitman/awesome-tunneling/blob/master/README.md
  - List of ngrok, Cloudflare Tunnel, Tailscale, and ZeroTier alternatives and other tunneling software and services. Focus on self-hosting.
- **[zhuima/awesome-cloudflare](https://github.com/zhuima/awesome-cloudflare)** — 15456⭐,最近推送 90 天前,匹配词: cloudflare
  - ℹ️ No CONTRIBUTING file — check the README's 'Contributing' section: https://github.com/zhuima/awesome-cloudflare/blob/master/README.md
  - ⛅️ 精选的 Cloudflare 工具、开源项目、指南、博客和其他资源列表。/ ⛅️ A curated list of Cloudflare tools, open source projects, guides, blogs and other resources.
- **[irazasyed/awesome-cloudflare](https://github.com/irazasyed/awesome-cloudflare)** — 1244⭐,最近推送 241 天前,匹配词: cloudflare
  - 📖 贡献指南: https://github.com/irazasyed/awesome-cloudflare/blob/master/contributing.md
  - ⛅️ Curated list of awesome Cloudflare worker recipes, open-source projects, guides, blogs and other resources.
- **[theoephraim/awesome-cloudflare-selfhosted](https://github.com/theoephraim/awesome-cloudflare-selfhosted)** — 1112⭐,最近推送 1 天前,匹配词: cloudflare
  - 📖 贡献指南: https://github.com/theoephraim/awesome-cloudflare-selfhosted/blob/main/CONTRIBUTING.md
  - 🍊☁️ Open-source* apps that replace SaaS product + tools, running in your own Cloudflare account
- **[tobilg/awesome-cloudflare-containers](https://github.com/tobilg/awesome-cloudflare-containers)** — 103⭐,最近推送 460 天前,匹配词: cloudflare
  - 📖 贡献指南: https://github.com/tobilg/awesome-cloudflare-containers/blob/main/CONTRIBUTING.md

## 六、可直接复制的修改文案

### 1) About 描述(GitHub 仓库页 → About → 编辑)

```
给 cmliu/edgetunnel 套一层本地 Web 向导，一键将 VLESS+WS+TLS 节点部署到 Cloudflare Pages：自动优选 CF IP、生成 Clash 订阅链接、管理后台自托管。Self-hosted GUI for one-click edgetunnel deploy with best-IP selection.
```

### 2) Topics 建议列表(逗号分隔,直接粘贴)

```
edgetunnel, mihomo, shadowsocks, clash-meta, windows, hysteria, hysteria2, vmess, ai, self-hosted
```
- Dropped as too crowded: clash, cloudflare, cloudflare-pages, cloudflare-workers, nodejs, proxy, subscription
- Added from comparable-repo co-occurrence: mihomo, shadowsocks, clash-meta, windows, hysteria, hysteria2

### 3) README 首屏改写示例

```markdown
# Cloudflare-Edgetunnel

> One sentence: what it is + the problem it solves (include: cf, clash, click).

[badge row: build status | license | stars]

![demo](./docs/demo.gif)  <!-- a 10-20s GIF beats three paragraphs -->

## Why
[2-3 bullets: the pain point, how this solves it, what's different]

## Quickstart
```bash
# one copy-pasteable command that gets to a working result
```
```

## 限制与说明

- Analyzed first 8 of 10 topics (raise with --max-topics).

---
*评分为方向性启发式,非 GitHub 官方排名权重。方法论与部分检查项改编自 [Bhanunamikaze/Agentic-SEO-Skill](https://github.com/Bhanunamikaze/Agentic-SEO-Skill)(MIT),topic 共现方法参考 [agentic-devrel/github-topic-recommender](https://github.com/agentic-devrel/github-topic-recommender)。*
