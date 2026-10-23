import tempfile
import unittest
from unittest.mock import Mock, patch
import pandas as pd
import requests
from ai_research import summarize, check_ollama
from monitor_settings import save_settings


class OllamaTests(unittest.TestCase):
    def args(self):
        return ({'symbol':'BTCUSDT','interval':'1h','mode':'demo'},
                {'frame':pd.DataFrame([{'close_time':'2026-10-23'}]),'score':0,
                 'side':'WAIT','factors':[],'reasons':['fixture']}, [])

    @patch('ai_research.requests.post')
    def test_local_does_not_forward_key_or_use_cloud(self, post):
        post.return_value = Mock(ok=True, json=lambda:{'message':{'content':'模擬研究'}})
        text = summarize(*self.args(), api_key='secret-never-forward', provider='ollama', model='qwen3:4b')
        self.assertEqual(text,'模擬研究')
        url = post.call_args.args[0]
        self.assertEqual(url,'http://127.0.0.1:11434/api/chat')
        self.assertNotIn('secret-never-forward',repr(post.call_args))
        self.assertFalse(post.call_args.kwargs['json']['stream'])

    @patch('ai_research.requests.post', side_effect=requests.Timeout)
    def test_local_failure_never_falls_back(self, post):
        with self.assertRaisesRegex(RuntimeError,'未切換雲端'):
            summarize(*self.args(), provider='ollama')
        self.assertEqual(post.call_count,1)

    @patch('ai_research.requests.get')
    def test_inventory_requires_installed_model(self, get):
        get.return_value = Mock(json=lambda:{'models':[{'name':'qwen3:4b'}]})
        self.assertEqual(check_ollama("qwen3:4b"),['qwen3:4b'])
        with self.assertRaisesRegex(ValueError,'尚未安裝'):
            check_ollama('qwen3:8b')

    @patch('ai_research.requests.post')
    def test_malformed_response_is_readable(self, post):
        post.return_value = Mock(ok=True, json=lambda:{})
        with self.assertRaisesRegex(RuntimeError,'格式異常'):
            summarize(*self.args(), provider='ollama')

    def test_local_default_and_cloud_model_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(save_settings({},root)['ai_provider'],'ollama')
            with self.assertRaises(ValueError):
                save_settings({'ollama_model':'qwen3:cloud'},root)

    @patch('ai_research.requests.post')
    def test_openai_requires_explicit_provider(self, post):
        post.return_value = Mock(ok=True,json=lambda:{'choices':[{'message':{'content':'研究'}}]})
        self.assertEqual(summarize(*self.args(),api_key='fake',provider='openai'),'研究')
        self.assertTrue(post.call_args.args[0].startswith('https://api.openai.com/'))
