# -*- coding: utf-8 -*-
"""
Sync assets between web templates/static and Android main assets.
- syncs index.html with local asset references
- bundles whitepaper (최종정리.html) as report.html with sticky mobile nav bar
"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_INDEX = ROOT_DIR / "mobile" / "templates" / "index.html"
ASSET_INDEX = ROOT_DIR / "mobile" / "app" / "src" / "main" / "assets" / "index.html"
SOURCE_REPORT = ROOT_DIR / "최종정리.html"
STATIC_REPORT = ROOT_DIR / "mobile" / "static" / "report.html"
ASSET_REPORT = ROOT_DIR / "mobile" / "app" / "src" / "main" / "assets" / "report.html"

def sync_index():
    with open(TEMPLATE_INDEX, "r", encoding="utf-8") as f:
        content = f.read()

    asset_content = content.replace('src="/static/dtc_ondevice_engine.js"', 'src="dtc_ondevice_engine.js"')
    asset_content = asset_content.replace('src="/static/vis-network.min.js"', 'src="vis-network.min.js"')

    ASSET_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(ASSET_INDEX, "w", encoding="utf-8") as f:
        f.write(asset_content)
    print(f"Updated Android assets index.html successfully ({len(asset_content):,} bytes)")

def sync_report():
    if not SOURCE_REPORT.exists():
        print(f"Warning: {SOURCE_REPORT} does not exist.")
        return

    with open(SOURCE_REPORT, "r", encoding="utf-8") as f:
        html = f.read()

    mobile_nav_header = """
<!-- DTC Mobile 전용 상단 복귀 내비게이션 바 -->
<div class="mobile-back-bar" style="position: sticky; top: 0; z-index: 9999; background: rgba(15, 23, 42, 0.96); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); color: #fff; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255, 255, 255, 0.12); box-shadow: 0 4px 12px rgba(0,0,0,0.18);">
  <a href="index.html" style="color: #38bdf8; text-decoration: none; font-weight: 700; font-size: 13px; display: inline-flex; align-items: center; gap: 6px;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
    DTC Mobile 진단으로 복귀
  </a>
  <span style="font-size: 11px; font-weight: 700; color: #34d399; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); padding: 3px 8px; border-radius: 980px; display: inline-flex; align-items: center; gap: 4px;"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>100% 오프라인 해설서</span>
</div>
"""

    mobile_responsive_css = """
<style>
body { margin: 0 !important; padding: 0 0 30px 0 !important; }
.mobile-back-bar {
  position: sticky;
  top: 0;
  left: 0;
  right: 0;
  width: 100%;
  z-index: 99999;
  background: #0f172a !important;
  color: #fff !important;
  padding: 10px 14px;
  display: flex !important;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 4px 12px rgba(0,0,0,0.18);
  box-sizing: border-box;
}
@media (max-width: 600px) {
  body { font-size: 13px !important; line-height: 1.6 !important; }
  .container { padding: 8px !important; width: 100% !important; max-width: 100% !important; }
  header { padding: 22px 14px !important; border-radius: 0 0 14px 14px !important; margin-bottom: 14px !important; }
  header h1 { font-size: 17px !important; line-height: 1.35 !important; }
  header p { font-size: 11.5px !important; }
  .enterprise-toolbar { flex-direction: column !important; gap: 8px !important; }
  .tool-btn-group { width: 100% !important; justify-content: space-between !important; }
  .tab-nav { overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; padding: 4px !important; scrollbar-width: none !important; }
  .tab-nav::-webkit-scrollbar { display: none !important; }
  .tab-btn { font-size: 11px !important; padding: 6px 9px !important; white-space: nowrap !important; flex-shrink: 0 !important; }
  table { display: block !important; width: 100% !important; overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }
  .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr !important; }
}
</style>
</head>
"""

    if "</head>" in html:
        html = html.replace("</head>", mobile_responsive_css, 1)

    if "<body>" in html:
        html = html.replace("<body>", "<body>\n" + mobile_nav_header, 1)

    html = html.replace('href="/" class="tool-btn primary"', 'href="index.html" class="tool-btn primary"')

    STATIC_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(STATIC_REPORT, "w", encoding="utf-8") as f:
        f.write(html)

    ASSET_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(ASSET_REPORT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated mobile static & android assets report.html successfully ({len(html):,} bytes)")

def sync_engine():
    source_engine = ROOT_DIR / "mobile" / "static" / "dtc_ondevice_engine.js"
    asset_engine = ROOT_DIR / "mobile" / "app" / "src" / "main" / "assets" / "dtc_ondevice_engine.js"
    if source_engine.exists():
        with open(source_engine, "r", encoding="utf-8") as f:
            content = f.read()
        asset_engine.parent.mkdir(parents=True, exist_ok=True)
        with open(asset_engine, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated Android assets dtc_ondevice_engine.js successfully ({len(content):,} bytes)")

if __name__ == "__main__":
    sync_index()
    sync_engine()
    sync_report()
