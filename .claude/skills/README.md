# Vendored YTrends skills

These three skills are vendored (copied) from the official
[YTuong/ytrends-skills](https://github.com/YTuong/ytrends-skills) repo (MIT
license) because `/plugin install` isn't available in the VS Code Claude Code
extension.

- **whats-hot** — weekly Etsy market scan (rising/cooling niches + seasonal events)
- **should-i-sell** — GO / CONDITIONAL GO / NO-GO verdict for a specific niche
- **holiday-prep** — seasonal launch timeline with rank-lag deadline math

They call the official **YTrends MCP** tools registered in `../../.mcp.json`
(server `ytrends`). Approve that server once, then invoke a skill by name
(e.g. "what's hot this week?") or as a slash command.

To update them later: re-clone the upstream repo and copy `skills/*` here.
