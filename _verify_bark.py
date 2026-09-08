import os, sys
sys.path.insert(0, r"G:\daily_stock_analysis")
from types import SimpleNamespace
from dotenv import load_dotenv
from src.notification_sender.bark_sender import BarkSender

load_dotenv(r"G:\daily_stock_analysis\.env")
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)

with open(r"G:\daily_stock_analysis\reports\report_20260730.md", encoding="utf-8") as f:
    md = f.read()

cfg = SimpleNamespace(
    bark_url=os.getenv("BARK_URL"),
    bark_device_key=os.getenv("BARK_DEVICE_KEY"),
    bark_sound=os.getenv("BARK_SOUND"),
    bark_level=os.getenv("BARK_LEVEL"),
    bark_group=os.getenv("BARK_GROUP"),
    webhook_verify_ssl=True,
)
ok = BarkSender(cfg).send_to_bark(md, title="📲 iPhone适配纯文本(最终) - 2026-07-30")
print("推送结果:", "成功" if ok else "失败")
