"""Explicitly managed, append-only local session revisions; SQLite CAS transactions."""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

def canonical(messages):
    return json.dumps(messages,ensure_ascii=False,separators=(",",":"),allow_nan=False)

def digest(messages):
    return hashlib.sha256(canonical(messages).encode("utf-8")).hexdigest()

def validate_messages(messages):
    if not isinstance(messages,list) or not messages:
        raise ValueError("nonempty messages required")
    for m in messages:
        if not isinstance(m,dict) or set(m)!={"role","content"} or m["role"] not in ("system","user","assistant") or not isinstance(m["content"],str):
            raise ValueError("only plain text messages supported")
    if len(canonical(messages).encode("utf-8"))>32*1024*1024:
        raise ValueError("session too large")
    return messages

class Conflict(ValueError):
    pass

class Store:
    def __init__(self,root):
        root=Path(root)
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=root/"ace-sessions.sqlite3"
        if self.path.is_symlink():
            raise ValueError("session DB must not be a symbolic link")
        # The state directory must be private to the local account; Windows ACLs
        # are the operator's responsibility. Do not store secrets in prompts.
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS revisions (sid TEXT, rev INTEGER, parent INTEGER, body TEXT NOT NULL, sha TEXT NOT NULL, action TEXT NOT NULL, PRIMARY KEY(sid,rev))")
            db.execute("CREATE TABLE IF NOT EXISTS heads (sid TEXT PRIMARY KEY, rev INTEGER NOT NULL, semantic INTEGER NOT NULL)")
        if os.name!="nt":
            os.chmod(self.path,0o600)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def check_id(sid):
        if not isinstance(sid,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",sid):
            raise ValueError("invalid session ID")

    def _read(self,db,sid,revision=None):
        self.check_id(sid)
        head=db.execute("SELECT rev,semantic FROM heads WHERE sid=?",(sid,)).fetchone()
        if head is None:
            raise ValueError("unknown session")
        rev=head[0] if revision is None else revision
        if type(rev) is not int or rev<0:
            raise ValueError("invalid revision")
        row=db.execute("SELECT body,sha,action FROM revisions WHERE sid=? AND rev=?",(sid,rev)).fetchone()
        if row is None:
            raise ValueError("unknown revision")
        messages=validate_messages(json.loads(row[0]))
        if digest(messages)!=row[1]:
            raise ValueError("archive checksum mismatch")
        return {"session":sid,"revision":rev,"head":head[0],"sha256":row[1],
                "allow_semantic":bool(head[1]),"messages":messages,"action":row[2]}

    def read(self,sid,revision=None):
        with self.connect() as db:
            return self._read(db,sid,revision)

    def create(self,sid,messages,allow_semantic=False):
        self.check_id(sid)
        validate_messages(messages)
        if type(allow_semantic) is not bool:
            raise ValueError("invalid consent")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM heads WHERE sid=?",(sid,)).fetchone():
                raise Conflict("session already exists")
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)",(sid,0,None,canonical(messages),digest(messages),"create"))
            db.execute("INSERT INTO heads VALUES(?,?,?)",(sid,0,int(allow_semantic)))
            return self._read(db,sid)

    def commit(self,sid,expected_revision,expected_sha,messages,action):
        validate_messages(messages)
        if type(expected_revision) is not int or not isinstance(expected_sha,str):
            raise ValueError("expected revision and SHA required")
        if action not in ("append","compact","rollback"):
            raise ValueError("invalid action")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old=self._read(db,sid)
            if old["revision"]!=expected_revision or old["sha256"]!=expected_sha:
                raise Conflict("session changed; reload and plan again")
            if action=="compact" and not old["allow_semantic"]:
                raise ValueError("semantic compaction not authorized")
            if action=="append" and messages[:len(old["messages"])]!=old["messages"]:
                raise ValueError("append must preserve previous messages")
            rev=expected_revision+1
            db.execute("INSERT INTO revisions VALUES(?,?,?,?,?,?)",(sid,rev,expected_revision,canonical(messages),digest(messages),action))
            db.execute("UPDATE heads SET rev=? WHERE sid=?",(rev,sid))
            return self._read(db,sid)

    def rollback(self,sid,expected_revision,expected_sha,target):
        old=self.read(sid,target)
        if old["revision"]>expected_revision:
            raise ValueError("cannot restore future revision")
        return self.commit(sid,expected_revision,expected_sha,old["messages"],"rollback")
