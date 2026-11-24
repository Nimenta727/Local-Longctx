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
