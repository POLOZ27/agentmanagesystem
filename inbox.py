"""加密收件箱：资料可以加密后放到服务器上，只有系统解锁后才能打开；导入前必须由主人预览并确认。

  解锁时生成一对 X25519 密钥：私钥用数据密钥加密存进保险库，公钥明文写到 <数据目录>/inbox.pub。
  投递方用公钥加密（临时密钥 ECDH → HKDF → AES-256-GCM），分块放进 <数据目录>/inbox/。
  服务器上任何时候都没有明文。能碰到服务器文件的人也能往这里放包，所以绝不自动导入：
  页面先列出包里的代理、收款信息和合同，主人确认后才写入。

包的格式：<名字>.json（份数、密文 sha256）+ <名字>.part001…，解密后是一个 zip：
  workbook.xlsx（佣金总表）、contracts/*（已签合同）、tracker.xlsx（潜在代理名单，可选）
"""
import base64
import hashlib
import io
import json
import os
import re
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"JAINBOX1"
RAW = dict(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _key(shared, eph_pub):
    return HKDF(hashes.SHA256(), 32, salt=eph_pub, info=b"ja-agent-portal inbox").derive(shared)


def seal(pub_b64: str, data: bytes) -> bytes:
    """投递方用：只需要公钥。"""
    pub = X25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(**RAW)
    nonce = os.urandom(12)
    return MAGIC + eph_pub + nonce + AESGCM(_key(eph.exchange(pub), eph_pub)).encrypt(nonce, data, MAGIC)


def _unseal(priv, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("不是收件箱的包")
    eph_pub, nonce, ct = blob[8:40], blob[40:52], blob[52:]
    shared = priv.exchange(X25519PublicKey.from_public_bytes(eph_pub))
    return AESGCM(_key(shared, eph_pub)).decrypt(nonce, ct, MAGIC)


def directory(vault):
    return os.path.join(vault.dir, "inbox")


def ensure_key(vault):
    """解锁后调用：第一次生成密钥对；保证 inbox.pub 和 inbox/ 存在（服务器上的 polo 账号要能往里放包）。"""
    from vault import _seal
    pub = vault._meta("inbox_pub")
    if not pub:
        priv = X25519PrivateKey.generate()
        raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
        vault._set_meta("inbox_priv", base64.b64encode(_seal(vault._need(), raw, b"inbox")).decode())
        pub = base64.b64encode(priv.public_key().public_bytes(**RAW)).decode()
        vault._set_meta("inbox_pub", pub)
    d = directory(vault)
    os.makedirs(d, exist_ok=True)
    os.chmod(d, 0o777)  # 里面只会有密文
    with open(os.path.join(vault.dir, "inbox.pub"), "w") as f:
        f.write(pub + "\n")
    return pub


def bundles(vault):
    """收件箱里的包：[{name, parts, complete}]。"""
    d = directory(vault)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        name = f[:-5]
        if not f.endswith(".json") or not NAME_RE.match(name):
            continue
        try:
            with open(os.path.join(d, f)) as fh:
                man = json.load(fh)
            n = int(man["parts"])
        except (ValueError, KeyError, OSError):
            continue
        have = sum(os.path.exists(os.path.join(d, f"{name}.part{i:03d}")) for i in range(1, n + 1))
        out.append({"name": name, "parts": n, "have": have, "complete": have == n, "sha256": man.get("sha256", "")})
    return out


def _files(vault, name):
    if not NAME_RE.match(name):
        raise ValueError("包名不对")
    d = directory(vault)
    with open(os.path.join(d, name + ".json")) as f:
        man = json.load(f)
    parts = [os.path.join(d, f"{name}.part{i:03d}") for i in range(1, int(man["parts"]) + 1)]
    return man, parts, os.path.join(d, name + ".json")


def open_bundle(vault, name) -> zipfile.ZipFile:
    """解密成内存里的 zip（不落盘）。"""
    from vault import _open
    man, parts, _ = _files(vault, name)
    blob = b"".join(open(p, "rb").read() for p in parts)
    if hashlib.sha256(blob).hexdigest() != man["sha256"]:
        raise ValueError("包不完整或被改动过（校验不符），请重新投递")
    priv = X25519PrivateKey.from_private_bytes(
        _open(vault._need(), base64.b64decode(vault._meta("inbox_priv")), b"inbox"))
    return zipfile.ZipFile(io.BytesIO(_unseal(priv, blob)))


def remove(vault, name):
    _, parts, man_path = _files(vault, name)
    for p in parts + [man_path]:
        try:
            os.remove(p)
        except OSError:
            pass
