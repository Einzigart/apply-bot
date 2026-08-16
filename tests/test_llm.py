"""Tests for OpenAI-compatible LLM configuration, completions, and scoring."""
import json
import unittest.mock as mock

from src.letter import render_llm
from src.llm import complete, get_llm_config
from src.score import llm_score


def test_get_llm_config_defaults():
    cfg = {}
    conf = get_llm_config(cfg)
    assert conf["base_url"] == "https://api.openai.com/v1"
    assert conf["api_key"] == ""
    assert conf["model"] == "gpt-4o-mini"
    assert conf["prefix"] == ""


def test_get_llm_config_from_yaml_llm_section():
    cfg = {
        "llm": {
            "endpoint": "https://openrouter.ai/api/v1/",
            "api_key": "sk-or-test",
            "model": "meta-llama/llama-3.3-70b-instruct",
            "prefix": "deepseek/",
        }
    }
    conf = get_llm_config(cfg)
    assert conf["base_url"] == "https://openrouter.ai/api/v1"
    assert conf["api_key"] == "sk-or-test"
    assert conf["model"] == "deepseek/meta-llama/llama-3.3-70b-instruct"
    assert conf["prefix"] == "deepseek/"


def test_get_llm_config_prefix_without_trailing_slash():
    cfg = {
        "llm": {
            "model": "gemini-3.7-flash-high",
            "prefix": "ag",
        }
    }
    conf = get_llm_config(cfg)
    assert conf["model"] == "ag/gemini-3.7-flash-high"
    assert conf["prefix"] == "ag"


def test_get_llm_config_prefix_deduplication():
    cfg = {
        "llm": {
            "model": "ag/gemini-3.7-flash-high",
            "prefix": "ag",
        }
    }
    conf = get_llm_config(cfg)
    assert conf["model"] == "ag/gemini-3.7-flash-high"



def test_get_llm_config_env_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("OPENAI_MODEL_PREFIX", "groq/")

    cfg = {
        "llm": {
            "endpoint": "https://api.openai.com/v1",
            "api_key": "old-key",
            "model": "old-model",
            "prefix": "",
        }
    }
    conf = get_llm_config(cfg)
    assert conf["base_url"] == "https://api.groq.com/openai/v1"
    assert conf["api_key"] == "gsk-test"
    assert conf["model"] == "groq/llama-3.3-70b-versatile"
    assert conf["prefix"] == "groq/"


def test_complete_urllib_fallback(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "openai", None)

    cfg = {
        "llm": {
            "endpoint": "https://mock.llm.com/v1",
            "api_key": "test-key",
            "model": "test-model",
        }
    }

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from mock LLM!",
                }
            }
        ]
    }

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def read(self):
            return json.dumps(mock_response_data).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=MockResponse()) as mock_urlopen:
        result = complete([{"role": "user", "content": "hi"}], cfg)
        assert result == "Hello from mock LLM!"
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://mock.llm.com/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer test-key"


def test_complete_openai_sdk():
    cfg = {
        "llm": {
            "endpoint": "https://api.openai.com/v1",
            "api_key": "test-key",
            "model": "gpt-4o-mini",
        }
    }

    mock_choice = mock.MagicMock()
    mock_choice.message.content = "Hello from openai SDK!"
    mock_resp = mock.MagicMock()
    mock_resp.choices = [mock_choice]

    with mock.patch("openai.OpenAI") as mock_openai_cls:
        mock_client = mock.MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai_cls.return_value = mock_client

        result = complete([{"role": "user", "content": "hi"}], cfg)
        assert result == "Hello from openai SDK!"
        mock_client.chat.completions.create.assert_called_once()


def test_llm_score_with_mocked_llm():
    cfg = {
        "scoring": {
            "match_threshold": 0.60,
            "borderline_band": [0.50, 0.70],
        },
        "filters": {
            "max_years_experience": 1,
        },
        "llm": {
            "endpoint": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "test-key",
        },
    }
    jobs = [
        {
            "jobstreet_id": "1001",
            "title": "Junior Data Analyst",
            "company": "PT Data Indo",
            "location": "Jakarta",
            "description": "SQL and Python required. 0-1 years.",
        }
    ]
    profile_yaml = "name: Jane Doe\nskills: [Python, SQL]"

    mock_llm_json = json.dumps([
        {
            "job_id": "1001",
            "match_pct": 80,
            "years_required": 1,
            "seniority": "junior",
            "met": ["Python", "SQL"],
            "unmet": [],
            "apply": True,
            "reason": "Strong match on core skills",
        }
    ])

    with mock.patch("src.score.complete", return_value=mock_llm_json):
        verdicts = llm_score(jobs, profile_yaml, cfg)
        assert len(verdicts) == 1
        v = verdicts[0]
        assert v["decision"] == "apply"
        assert v["match_pct"] == 80
        assert v["model"] == "gpt-4o-mini"
        assert "Strong match on core skills" in v["reason"]


def test_render_llm_letter_success():
    cfg = {"llm": {"model": "gpt-4o-mini"}}
    profile = {
        "name": "Farid",
        "letter": {
            "pitch": "CS grad with Python/ML skills",
            "middles": {"general": "General fallback."},
        },
    }

    with mock.patch("src.letter.complete", return_value="I am excited to bring my Python and machine learning skills to PT ABC."):
        letter = render_llm("Data Analyst", "PT ABC", "Python required", cfg, profile)
        assert "I am excited to bring my Python and machine learning skills to PT ABC." in letter
        assert "Farid" in letter
        assert "PT ABC" in letter
