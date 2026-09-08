import os, sys, base64, subprocess
sys.path.insert(0, r"G:\daily_stock_analysis")
from dotenv import load_dotenv
from urllib.parse import urlparse
from markdown_it import MarkdownIt
from PIL import Image
import requests

ROOT = r"G:\daily_stock_analysis"
TMP = os.path.join(ROOT, ".workbuddy", "tmp")
os.makedirs(TMP, exist_ok=True)
MD_PATH = os.path.join(ROOT, "reports", "report_20260730.md")
HTML_PATH = os.path.join(TMP, "report_20260730.html")
PNG_PATH = os.path.join(TMP, "report_20260730.png")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; padding: 26px 22px; width: 720px;
  background: #ffffff; color: #1f2329;
  font-family: "Microsoft YaHei", "微软雅黑", "SimHei", "黑体", sans-serif;
  font-size: 15px; line-height: 1.7;
}
h1 { font-size: 22px; color: #d4380d; border-bottom: 2px solid #ffd8bf; padding-bottom: 8px; margin-top: 0; }
h2 { font-size: 18px; color: #cf1322; margin-top: 22px; }
h3 { font-size: 16px; color: #333; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 14px; }
th, td { border: 1px solid #d9d9d9; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #fff7e6; }
blockquote { border-left: 4px solid #91d5ff; margin: 10px 0; padding: 4px 12px; color: #555; background: #f5faff; }
code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
ul, ol { padding-left: 22px; }
hr { border: none; border-top: 1px solid #eee; }
strong { color: #c41d7f; }
em { color: #555; }
"""

md_text = open(MD_PATH, encoding="utf-8").read()
md = MarkdownIt().enable("table")
body_html = md.render(md_text)
full_html = ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'><style>"
            + CSS + "</style></head><body>" + body_html + "</body></html>")
open(HTML_PATH, "w", encoding="utf-8").write(full_html)
print("HTML written:", HTML_PATH)

# Chrome headless 全页截图
file_url = "file:///" + HTML_PATH.replace("\\", "/")
subprocess.run(
    [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
     "--disable-dev-shm-usage", "--hide-scrollbars",
     "--force-color-profile=srgb",
     "--screenshot=" + PNG_PATH, "--window-size=720,12000", file_url],
    check=True, timeout=90,
)
raw_bytes = os.path.getsize(PNG_PATH)
img = Image.open(PNG_PATH)
print("raw screenshot:", img.size, f"{raw_bytes/1024:.0f} KB")

# 缩放 / 压缩以控制 base64 体积
max_w = 720
if img.width > max_w:
    ratio = max_w / img.width
    img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
img.save(PNG_PATH, "PNG", optimize=True)
sz = os.path.getsize(PNG_PATH)
ext = "png"
if sz > 1.2 * 1024 * 1024:  # 太大转 JPEG（白底文字图压缩率极高）
    img.convert("RGB").save(PNG_PATH, "JPEG", quality=82, optimize=True)
    sz = os.path.getsize(PNG_PATH)
    ext = "jpeg"
print("final image:", img.size, f"{sz/1024:.0f} KB", ext)

# base64 内嵌
with open(PNG_PATH, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
mime = "image/jpeg" if ext == "jpeg" else "image/png"
data_uri = f"data:{mime};base64,{b64}"
print("base64 length:", len(b64))

# 强制直连 Bark（绕过 .env 代理，api.day.app 直连通）
load_dotenv(os.path.join(ROOT, ".env"))
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)
bark_url = os.getenv("BARK_URL")
device_key = (os.getenv("BARK_DEVICE_KEY") or "").strip()
parsed = urlparse(bark_url)
if parsed.path and parsed.path.strip("/"):
    device_key = parsed.path.strip("/")
    endpoint = f"{parsed.scheme}://{parsed.netloc}/push"
else:
    endpoint = f"{bark_url.rstrip('/')}/push"
# Bark 官方服务器(api.day.app)对请求体有严格大小限制(413)，base64 内嵌图片极易超限。
# 阈值 80KB(base64) 仅作保护：超过则跳过推送，改用公网 URL 方案(见说明)。
if len(b64) > 80 * 1024:
    print(f"base64 {len(b64)/1024:.0f}KB 超过 Bark 官方限制，跳过内嵌推送。"
          f"要让手机出图需把图片放到公网 URL 再用 image=URL 推送(或自建 Bark 服务器)。")
else:
    payload = {
        "device_key": device_key,
        "title": "📊 股票分析报告(图片) 2026-07-30",
        "body": "📈 点击展开查看完整报告图片",
        "image": data_uri,
        "group": "daily_stock_analysis",
    }
    r = requests.post(endpoint, json=payload, timeout=40)
    print("Bark status:", r.status_code, r.text[:240])
