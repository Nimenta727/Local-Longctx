import unittest
from types import SimpleNamespace
from longctx.native_messages import prepare_native,validate_prompt
from longctx.planner import RequestError

class Backend:
    def json(self,path,body):
        assert path=="/v1/messages/count_tokens"
        self.body=body
        return {"input_tokens":128}

class NativeMessagesTests(unittest.TestCase):
    def setUp(self):
        self.c=SimpleNamespace(model_id="local-longctx",context=8192,output_reserve=512)
        self.b=Backend()
        self.req={"model":"local-longctx","max_tokens":256,"tools":[{"name":"read","input_schema":{"type":"object"}}],
                  "messages":[{"role":"user","content":"read a file"},
                  {"role":"assistant","content":[{"type":"tool_use","id":"call1","name":"read","input":{"path":"test.txt"}}]},
                  {"role":"user","content":[{"type":"tool_result","tool_use_id":"call1","content":"example"}]}]}
    def test_native_count_includes_tools(self):
        plan,body=prepare_native(self.req,self.c,self.b)
        self.assertEqual(plan.prompt_tokens,128)
        self.assertEqual(self.b.body["tools"],self.req["tools"])
        self.assertEqual(body,self.req)
        self.assertNotIn("max_tokens",self.b.body)
    def test_missing_or_duplicate_results(self):
        self.req["messages"].pop()
        with self.assertRaises(RequestError):
            prepare_native(self.req,self.c,self.b)
    def test_image_rejected(self):
        self.req["messages"]=[{"role":"user","content":[{"type":"image","source":{}}]}]
        with self.assertRaises(RequestError):
            prepare_native(self.req,self.c,self.b)
    def test_output_cap(self):
        self.req["max_tokens"]=513
        with self.assertRaises(RequestError):
            prepare_native(self.req,self.c,self.b)
    def test_context_overflow_is_identifiable_by_desktop_adapter(self):
        self.c.context = 512
        with self.assertRaisesRegex(RequestError, "input=128, output=256, margin=256, window=512"):
            prepare_native(self.req,self.c,self.b)
