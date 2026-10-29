"""加密保险库：所有业务数据只以密文形式落盘。

密钥层级
  主密码 --Argon2id--> KEK（密钥加密密钥，从不落盘）
  KEK --AES-256-GCM 解包--> DEK（数据密钥，只在内存中）
  DEK --AES-256-GCM--> 每条记录 / 每个合同文件

服务器磁盘、数据库备份里只有：盐、KDF 参数、被包裹的 DEK、密文。
没有主密码（或离线保存的恢复密钥），任何人包括服务器管理员都无法解密。
"""
import base64
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KDF = {"t": 3, "m": 64 * 1024, "p": 2}  # Argon2id：3 轮、64 MB 内存


def _kek(password: str, salt: bytes, kdf=KDF) -> bytes:
    return hash_secret_raw(password.encode(), salt, time_cost=kdf["t"], memory_cost=kdf["m"],
                           parallelism=kdf["p"], hash_len=32, type=Type.ID)


def _seal(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def _open(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad)


class Locked(Exception):
    pass


class Vault:
    def __init__(self, data_dir: str):
        self.dir = data_dir
        os.makedirs(os.path.join(data_dir, "files"), exist_ok=True)
        self.db_path = os.path.join(data_dir, "vault.db")
        self._dek = None
        self._cache = {}  # kind -> {id: dict}，解锁期间的明文缓存，只在内存
        self._lock = threading.RLock()
        with self._db() as c:
            c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, blob BLOB, updated REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS audit (ts REAL, event TEXT)")

    def _db(self):
        return sqlite3.connect(self.db_path)

    def _meta(self, k):
        with self._db() as c:
            row = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return json.loads(row[0]) if row else None

    def _set_meta(self, k, v):
        with self._db() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, json.dumps(v)))

    def audit(self, event):
        # 审计日志只记录事件类型和时间，不含业务数据
        with self._db() as c:
            c.execute("INSERT INTO audit VALUES (?,?)", (time.time(), event))

    def audit_log(self, n=50):
        with self._db() as c:
            return c.execute("SELECT ts, event FROM audit ORDER BY ts DESC LIMIT ?", (n,)).fetchall()

    # ---- 初始化 / 解锁 ----
    @property
    def initialized(self):
        return self._meta("wrapped_dek") is not None

    @property
    def unlocked(self):
        return self._dek is not None

    def initialize(self, password: str, totp_secret: str) -> str:
        """首次设置。返回恢复密钥（只显示一次，需离线保存）。"""
        if self.initialized:
            raise RuntimeError("already initialized")
        dek = AESGCM.generate_key(256)
        salt = os.urandom(16)
        recovery = secrets.token_bytes(32)
        self._set_meta("kdf", {**KDF, "salt": base64.b64encode(salt).decode()})
        self._set_meta("wrapped_dek", base64.b64encode(_seal(_kek(password, salt), dek, b"dek")).decode())
        self._set_meta("recovery_dek", base64.b64encode(_seal(recovery, dek, b"dek")).decode())
        self._dek = dek
        self._set_meta("totp", base64.b64encode(_seal(dek, totp_secret.encode(), b"totp")).decode())
        self.audit("vault initialized")
        return base64.b32encode(recovery).decode().rstrip("=")

    def try_unwrap(self, password: str):
        kdf = self._meta("kdf")
        try:
            return _open(_kek(password, base64.b64decode(kdf["salt"]), kdf),
                         base64.b64decode(self._meta("wrapped_dek")), b"dek")
        except Exception:
            return None

    def totp_secret(self, dek) -> str:
        return _open(dek, base64.b64decode(self._meta("totp")), b"totp").decode()

    def unlock(self, dek):
        with self._lock:
            self._dek = dek
            self._load_all()
        self.audit("unlocked")

    def lock(self):
        with self._lock:
            self._dek = None
            self._cache = {}
        self.audit("locked")

    def change_password(self, new_password: str):
        dek = self._need()
        salt = os.urandom(16)
        self._set_meta("kdf", {**KDF, "salt": base64.b64encode(salt).decode()})
        self._set_meta("wrapped_dek", base64.b64encode(_seal(_kek(new_password, salt), dek, b"dek")).decode())
        self.audit("password changed")

    def _need(self):
        if self._dek is None:
            raise Locked()
        return self._dek

    # ---- 记录 ----
    def _load_all(self):
        self._cache = {}
        with self._db() as c:
            for rid, kind, blob in c.execute("SELECT id, kind, blob FROM records"):
                self._cache.setdefault(kind, {})[rid] = json.loads(_open(self._dek, blob, rid.encode()))

    def all(self, kind):
        self._need()
        return list(self._cache.get(kind, {}).values())

    def get(self, kind, rid):
        self._need()
        return self._cache.get(kind, {}).get(rid)

    def put(self, kind, rec: dict):
        dek = self._need()
        rec.setdefault("id", uuid.uuid4().hex)
        rid = rec["id"]
        blob = _seal(dek, json.dumps(rec, ensure_ascii=False).encode(), rid.encode())
        with self._lock, self._db() as c:
            c.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?)", (rid, kind, blob, time.time()))
            self._cache.setdefault(kind, {})[rid] = rec
        return rec

    def delete(self, kind, rid):
        self._need()
        with self._lock, self._db() as c:
            c.execute("DELETE FROM records WHERE id=?", (rid,))
            self._cache.get(kind, {}).pop(rid, None)

    # ---- 文件（合同等） ----
    def put_file(self, data: bytes) -> str:
        fid = uuid.uuid4().hex  # 磁盘文件名是随机 ID，不暴露代理名或合同名
        with open(os.path.join(self.dir, "files", fid), "wb") as f:
            f.write(_seal(self._need(), data, fid.encode()))
        return fid

    def get_file(self, fid: str) -> bytes:
        with open(os.path.join(self.dir, "files", fid), "rb") as f:
            return _open(self._need(), f.read(), fid.encode())
