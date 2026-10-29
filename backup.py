"""加密备份：把保险库（已加密的数据库 + 已加密的文件）打包复制到 NAS。

备份里只有密文，复制、保管备份的人（包括技术人员和 NAS 管理员）都看不到内容；
恢复时仍然需要主密码 + 验证码（或恢复密钥）。所以备份不需要保险库解锁，
锁定状态下也照常每天运行。

备份目录用环境变量 AGENT_PORTAL_BACKUP_DIR 指定（例如 NAS 挂载点 /mnt/nas/agent-portal），
它只是一个路径，不是机密。
"""
import datetime as dt
import json
import os
import sqlite3
import tarfile
import tempfile
import threading
import time

KEEP_DAILY = 14     # 最近 14 天每天一份
KEEP_MONTHLY = 12   # 再往前每月留 1 份，保留 12 个月
STATUS = "backup-status.json"


def backup_dir():
    return os.environ.get("AGENT_PORTAL_BACKUP_DIR", "")


def status(data_dir):
    try:
        with open(os.path.join(data_dir, STATUS)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_status(data_dir, **kw):
    s = status(data_dir)
    s.update(kw)
    with open(os.path.join(data_dir, STATUS), "w") as f:
        json.dump(s, f)


def run(data_dir, dest=None, now=None):
    """做一次备份，返回备份文件路径。"""
    dest = dest or backup_dir()
    if not dest:
        raise RuntimeError("没有设置备份目录（AGENT_PORTAL_BACKUP_DIR）")
    if not os.path.isdir(dest):
        raise RuntimeError(f"备份目录不存在或 NAS 未挂载：{dest}")
    now = now or dt.datetime.now()
    name = f"agent-portal-{now:%Y%m%d-%H%M}.tar"
    path = os.path.join(dest, name)
    with tempfile.TemporaryDirectory() as tmp:
        snap = os.path.join(tmp, "vault.db")
        src = sqlite3.connect(os.path.join(data_dir, "vault.db"))
        dst = sqlite3.connect(snap)
        with dst:
            src.backup(dst)  # 在线一致性快照，备份时系统可以照常使用
        src.close()
        dst.close()
        with tarfile.open(path + ".part", "w") as tar:
            tar.add(snap, arcname="vault.db")
            files = os.path.join(data_dir, "files")
            if os.path.isdir(files):
                tar.add(files, arcname="files")
    os.replace(path + ".part", path)
    prune(dest, now.date())
    _write_status(data_dir, last_ok=now.isoformat(timespec="minutes"), last_file=name,
                  last_size=os.path.getsize(path), last_error=None)
    return path


def prune(dest, today):
    """保留最近 KEEP_DAILY 天的每日备份，更早的每月只留最后一份，最多 KEEP_MONTHLY 个月。"""
    items = []
    for n in os.listdir(dest):
        if n.startswith("agent-portal-") and n.endswith(".tar"):
            try:
                items.append((dt.datetime.strptime(n[13:26], "%Y%m%d-%H%M"), n))
            except ValueError:
                continue
    items.sort(reverse=True)
    keep, months = set(), {}
    for when, n in items:
        age = (today - when.date()).days
        if age < KEEP_DAILY:
            keep.add(n)
        else:
            months.setdefault(when.strftime("%Y-%m"), n)
    for m in sorted(months, reverse=True)[:KEEP_MONTHLY]:
        keep.add(months[m])
    for _, n in items:
        if n not in keep:
            os.remove(os.path.join(dest, n))


def listing(dest=None):
    dest = dest or backup_dir()
    if not dest or not os.path.isdir(dest):
        return []
    out = [(n, os.path.getsize(os.path.join(dest, n))) for n in os.listdir(dest)
           if n.startswith("agent-portal-") and n.endswith(".tar")]
    return sorted(out, reverse=True)


def start(data_dir, hour=2, check_every=600):
    """每天凌晨 hour 点后做一次备份。"""
    def loop():
        while True:
            try:
                s = status(data_dir)
                today = dt.date.today().isoformat()
                if backup_dir() and dt.datetime.now().hour >= hour and (s.get("last_ok") or "")[:10] != today:
                    run(data_dir)
            except Exception as e:  # 记下失败原因，设置页会显示
                _write_status(data_dir, last_error=f"{dt.datetime.now():%Y-%m-%d %H:%M} {e}")
            time.sleep(check_every)
    threading.Thread(target=loop, daemon=True).start()


def verify(vault, dest=None):
    """恢复演练：打开最新一份备份，用当前密钥逐条解密记录和文件（只在内存和临时目录里，不改动现有数据）。
    返回 {"file", "records", "files", "bad"}。"""
    from vault import _open
    items = listing(dest)
    if not items:
        raise RuntimeError("备份目录里还没有备份")
    name = items[0][0]
    dek = vault._need()
    tmpdir = "/dev/shm" if os.path.isdir("/dev/shm") else None
    with tempfile.TemporaryDirectory(dir=tmpdir) as tmp, tarfile.open(os.path.join(dest or backup_dir(), name)) as tar:
        tar.extract("vault.db", tmp, filter="data")
        db = sqlite3.connect(os.path.join(tmp, "vault.db"))
        recs = bad = 0
        for rid, blob in db.execute("SELECT id, blob FROM records"):
            try:
                json.loads(_open(dek, blob, rid.encode()))
                recs += 1
            except Exception:  # noqa: BLE001
                bad += 1
        db.close()
        files = 0
        for m in tar.getmembers():
            if m.isfile() and m.name.startswith("files/"):
                try:
                    _open(dek, tar.extractfile(m).read(), os.path.basename(m.name).encode())
                    files += 1
                except Exception:  # noqa: BLE001
                    bad += 1
    return {"file": name, "records": recs, "files": files, "bad": bad}
