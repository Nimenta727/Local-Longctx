import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from longctx.session_store import Store,Conflict
from longctx.managed import extract,compact_session
from longctx.telemetry import Metrics,path_value

class FakeBackend:
    def count_prompt(self,messages):
        return sum(len(m["content"]) for m in messages)+len(messages)*4

class ManagedTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name))
        self.messages=[{"role":"system","content":"Rules"},
                       {"role":"assistant","content":"ANCHOR\n"+"old repeated material\n"*600},
                       *[{"role":"user","content":"recent"} for _ in range(4)]]
        self.old=self.store.create("s",self.messages,True)
        self.c=SimpleNamespace(context=14000,output_reserve=128)
        self.metrics=Metrics(2,16,1,8,.93,200,0)
        self.body={"session":"s","expected_revision":0,"expected_sha":self.old["sha256"],
                   "telemetry_profile":{},"estimates":{"growth_tokens_per_second":100,
                    "history_dependency":.1,"compact_seconds":1,"expected_turns":10,
                    "prefix_recompute_tokens":100,"cache_hit_fraction":.1,
                    "seconds_since_compact":600,"compact_peak_ram_gib":.1,"compact_peak_vram_gib":.1},
                   "segments":[{"index":1,"pinned":False,"anchors":["ANCHOR"],"budget_chars":500,
                    "importance":.1,"access_frequency":.1,"dependency":.1}]}
    def sample(self,*args):
        return self.metrics
    def call(self,**kwargs):
        return compact_session(self.store,FakeBackend(),self.c,{**self.body,**kwargs},self.sample)
    def test_preview_commit_rollback(self):
        preview=self.call()
        self.assertFalse(preview["committed"])
        self.assertGreater(preview["saved_tokens"],0)
        self.assertEqual(self.store.read("s")["revision"],0)
        result=self.call(commit=True)
        self.assertTrue(result["committed"])
        saved=self.store.read("s")
        self.assertIn("ANCHOR",saved["messages"][1]["content"])
        self.assertEqual(saved["messages"][0],self.messages[0])
        self.assertEqual(saved["messages"][-4:],self.messages[-4:])
        self.assertEqual(self.store.read("s",0)["messages"],self.messages)
        restored=self.store.rollback("s",1,saved["sha256"],0)
        self.assertEqual(restored["messages"],self.messages)
        self.assertEqual(restored["revision"],2)
    def test_stale(self):
        self.call(commit=True)
        with self.assertRaises(Conflict):
            self.call(commit=True)
    def test_busy(self):
        self.metrics=replace(self.metrics,active_requests=1)
        self.assertEqual(self.call()["action"],"defer")
    def test_exact_default(self):
        original=self.store.create("exact",self.messages)
        result=self.call(session="exact",expected_sha=original["sha256"],commit=True)
        self.assertEqual(result["action"],"keep")
    def test_protected(self):
        with self.assertRaises(ValueError):
            extract("a\nb\n"*100,["not present"],100)
    def test_schema(self):
        self.assertEqual(path_value({"a":{"b":3}},["a","b"]),3)
        for value in ({}, {"a":{"b":float("nan")}}, {"a":{"b":True}}):
            with self.assertRaises(ValueError):
                path_value(value,["a","b"])

    def test_replay_task_state_and_recall(self):
        from longctx.managed import dispatch

        history = self.messages[1]["content"].splitlines()
        history[200:203] = [
            "Keep the public API stable.",
            "Rejected v2 migration because it drops legacy clients.",
            "decode_cache.py returned ERR_381. 缓存损坏需要重建。",
        ]
        messages = [*self.messages]
        messages[1] = {"role": "assistant", "content": "\n".join(history)}
        original = self.store.create("replay", messages, True)
        segment = self.body["segments"][0]
        legacy = self.call(session="replay", expected_sha=original["sha256"])
        self.assertNotIn("ERR_381", legacy["preview_messages"][1]["content"])
        self.assertNotIn("Rejected v2 migration", legacy["preview_messages"][1]["content"])
        result = self.call(
            session="replay", expected_sha=original["sha256"], commit=True,
            segments=[{**segment, "task_state": [
                {"kind": "constraint", "quote": "Keep the public API stable."},
                {"kind": "failed_attempt", "quote": "Rejected v2 migration"},
            ]}],
        )
        compacted = self.store.read("replay")
        self.assertIn("[constraint; source 0:1] Keep the public API stable.",
                      compacted["messages"][1]["content"])
        self.assertIn("[failed_attempt; source 0:1] Rejected v2 migration because it drops legacy clients.",
                      compacted["messages"][1]["content"])
        self.assertNotIn("ERR_381", compacted["messages"][1]["content"])

        def recall(budget, query, **kwargs):
            return dispatch(self.store, FakeBackend(), self.c, "/local/session/recall",
                            {"session": "replay", "query": query, "max_recall_tokens": budget, **kwargs})

        for query in ("Check decode_cache.py and ERR_381", "缓存损坏怎么处理"):
            recalled = recall(350, query)
            self.assertEqual(recalled["messages"][:-1], compacted["messages"])
            self.assertIn("ERR_381", recalled["messages"][-1]["content"])
            self.assertGreater(recalled["recall_tokens"], 0)
            self.assertLessEqual(recalled["recall_tokens"], 350)
            self.assertEqual(len(recalled["sources"]), 1)
            source = recalled["sources"][0]
            self.assertEqual((source["revision"], source["index"]), (0, 1))
            self.assertIn("ERR_381", messages[1]["content"][source["start"]:source["end"]])
            self.assertLess(recalled["input_tokens"],
                            FakeBackend().count_prompt(messages + [{"role": "user", "content": query}]))
        self.assertEqual(recall(1, "ERR_381")["sources"], [])
        self.assertEqual(self.store.read("replay")["revision"], 1)
        # Rollback restores the branch that belonged to each target.
        self.store.rollback("replay", 1, result["sha256"], 0)
        self.assertEqual(recall(350, "ERR_381")["sources"], [])
        self.store.rollback("replay", 2, original["sha256"], 1)
        self.assertTrue(recall(350, "ERR_381")["sources"])

    def test_protected_group(self):
        result = self.call(protected_groups=[[0, 1]])
        self.assertEqual(result["decision"]["candidates"], ())
        self.assertEqual(self.store.read("s")["messages"], self.messages)

    def test_warm_prefix_gate_expires_near_window(self):
        from longctx.compact import Snapshot, Segment, evaluate

        snapshot = Snapshot(7, 10, 8, 10, 8500, 10000, 100, 0, .85, .1, 100,
                            0, 50, 0, exact_mode=False, allow_semantic=True, cache_hit_fraction=.8)
        segment = Segment("1", 4000, .1, .1, .1, 0)
        self.assertEqual(evaluate(snapshot, [segment]).action, "keep")
        self.assertEqual(evaluate(replace(snapshot, context_tokens=9200), [segment]).action,
                         "propose_semantic_compact")

    def test_concept_recall_rebuilds_old_index_and_prioritizes_literal_result(self):
        history = [
            {"role": "user", "content": "Store the report."},
            {"role": "assistant", "content": (
                "备份：archive-only-17\n"
                "数据库恢复流程指定了此备份：snapshot-M61\n"
                "Exact database restore error ERR_381: snapshot-N88"
            )},
        ]
        original = self.store.create("upgrade", history, True)
        self.store.commit("upgrade", 0, original["sha256"], [
            history[0], {"role": "assistant", "content": "Archived report."},
        ], "compact")
        with self.store.connect() as db:
            db.execute("CREATE TABLE archive_indexed (sid TEXT, rev INTEGER, PRIMARY KEY(sid,rev))")
            db.execute("INSERT INTO archive_indexed VALUES ('upgrade', 1)")
        _, hits = self.store.recall("upgrade", None, "Which backup restores the database?")
        content = [hit["content"] for hit in hits]
        self.assertTrue(any("snapshot-M61" in value for value in content))
        self.assertFalse(any("archive-only-17" in value for value in content))
        _, hits = self.store.recall("upgrade", None, "Database backup ERR_381")
        self.assertIn("snapshot-N88", hits[0]["content"])

    def test_concurrent_appends_keep_one_head_and_close_connections(self):
        from concurrent.futures import ThreadPoolExecutor
        from sqlite3 import ProgrammingError
        from threading import Barrier

        start = Barrier(2)

        def append(content):
            start.wait(timeout=5)
            try:
                saved = self.store.commit("s", 0, self.old["sha256"],
                                          self.messages + [{"role": "user", "content": content}],
                                          "append")
                return saved["revision"]
            except Conflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            revisions = list(pool.map(append, ("first", "second")))
        self.assertCountEqual(revisions, [1, None])
        latest = self.store.read("s")
        self.assertEqual(latest["revision"], latest["head"])
        self.assertEqual(self.store.read("s", 0)["messages"], self.messages)
        with self.assertRaisesRegex(ValueError, "invalid target revision"):
            self.store.rollback("s", 1, latest["sha256"], None)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0], 2)
        with self.assertRaises(ProgrammingError):
            db.execute("SELECT 1")

    def test_exception_rolls_back_and_closes_session_connection(self):
        from sqlite3 import ProgrammingError

        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with self.store.connect() as db:
                db.execute("UPDATE heads SET rev=999 WHERE sid='s'")
                raise RuntimeError("interrupted")
        with self.assertRaises(ProgrammingError):
            db.execute("SELECT 1")
        self.assertEqual(self.store.read("s")["revision"], 0)
