# Bundled resources

- Apache ECharts **6.0.0**, unmodified `dist/echarts.min.js` from `https://registry.npmjs.org/echarts/-/echarts-6.0.0.tgz`. Apache-2.0; see ECHARTS-LICENSE.txt and ECHARTS-NOTICE.txt. Includes its bundled rendering dependencies.
- Noto Sans 400/500/600/700 (Google Fonts v42), and Noto Sans SC 500/700 (v41, subset containing the six Chinese UI glyphs 频谱分析星座). SIL Open Font License; licenses in `../assets/`. Font declarations and local file mapping in `../css/fonts.css`.
- `../assets/ideal.svg` and `recovered.svg`: original legend assets returned by Figma MCP for frame 4:29 in `dAMCnMXgfY8clmRMgLPWyS`, retrieved 2026-10-09. Used in the original Results legend positions. Data plot SVGs were intentionally replaced by real ECharts series per the task specification.

No remote runtime resource URLs, CDN requirement, or frontend build step.
