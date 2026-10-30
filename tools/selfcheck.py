"""部署后自检（在容器里运行）：生成一份虚构代理的测试合同，转成 PDF 和预览图。不读写任何真实数据。"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import contracts
    import PIL  # noqa: F401  预览图需要
    import psycopg  # noqa: F401  官网入学申请需要
    a = {"name": "Selfcheck Agency", "legal_name": "Selfcheck Ltd.", "code": "J200000", "email": "x@example.com"}
    _, data = contracts.generate(a, "standard", dt.date(2026, 1, 1), dt.date(2028, 12, 31), renew=True)
    pdf = contracts.to_pdf(data)
    assert pdf, "LibreOffice 没有转出 PDF"
    n = contracts.page_count(pdf)
    assert n >= 4, f"PDF 只有 {n} 页"
    png = contracts.page_png(pdf, 0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "预览图不是 PNG"
    print(f"合同自检：通过（{n} 页，预览图正常）")
except Exception as e:  # noqa: BLE001
    print(f"合同自检：失败 —— {type(e).__name__}: {e}")
    sys.exit(1)
