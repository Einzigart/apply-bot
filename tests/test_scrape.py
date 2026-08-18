"""Teaser parsing locked to real card texts captured from id.jobstreet.com
on 2026-08-15 (data-analyst-jobs/in-Jakarta), plus Redux JSON extraction and markdown conversion."""
from src.scrape import (
    _guess_company,
    _guess_location,
    _guess_salary,
    _title_from_teaser,
    extract_seek_redux_data,
    html_to_markdown,
    scrape_detail_http,
    scrape_serp_http,
)

CARD_1 = ("Listed more than nineteen days ago\nData Analyst\ndi\nPT United Dico Citas\n\n"
          "Ini adalah lowongan kerja Full time\n\nJakarta Raya\nBergabunglah sebagai "
          "Data Analyst di PT United Dico Citas.")

CARD_2 = ("Listed more than nine days ago\nJunior Data Analyst\ndi\nPT YHS Indonesia\n\n"
          "Ini adalah lowongan kerja Full time\n\nJakarta Raya\nRp\xa06.500.000 – "
          "Rp\xa07.000.000 per month\nKandidat diharapkan mampu menganalisis data")

CARD_3 = ("Listed more than nine days ago\nData Analyst\ndi\nPT Ayo Indonesia Maju "
          "(ayo.co.id)\nDibutuhkan segera\n\nIni adalah lowongan kerja Full time\n\n"
          "Jakarta Pusat, Jakarta Raya(Hibrid)\nRp\xa012.000.000 – Rp\xa018.000.000 "
          "per month")


def test_title():
    assert _title_from_teaser(CARD_1) == "Data Analyst"
    assert _title_from_teaser(CARD_2) == "Junior Data Analyst"


def test_company():
    assert _guess_company(CARD_1) == "PT United Dico Citas"
    assert _guess_company(CARD_3) == "PT Ayo Indonesia Maju (ayo.co.id)"


def test_location():
    assert _guess_location(CARD_1, {}) == "Jakarta Raya"
    assert _guess_location(CARD_3, {}) == "Jakarta Pusat, Jakarta Raya(Hibrid)"


def test_location_not_confused_by_company_name():
    assert _guess_location(CARD_2, {}) == "Jakarta Raya"  # not "PT YHS Indonesia"


def test_salary():
    assert _guess_salary(CARD_1) is None
    assert "7.000.000" in _guess_salary(CARD_2)


def test_html_to_markdown():
    sample_html = """
    <div>
        <h3>Job Description</h3>
        <p>Requirements:</p>
        <ul>
            <li>Min 1 year experience in Python &amp; SQL</li>
            <li>Familiar with FastAPI</li>
        </ul>
    </div>
    """
    md = html_to_markdown(sample_html)
    assert "Job Description" in md
    assert "Requirements:" in md
    assert "- Min 1 year experience in Python & SQL" in md
    assert "- Familiar with FastAPI" in md


def test_extract_seek_redux_data():
    raw_html = (
        '<html><body><script>window.SEEK_REDUX_DATA = {"results": {"results": {"jobs": [{"id": "123", "title": "Dev"}]}}};</script></body></html>'
    )
    data = extract_seek_redux_data(raw_html)
    assert data is not None
    assert data["results"]["results"]["jobs"][0]["id"] == "123"


def test_extract_seek_redux_data_missing():
    raw_html = "<html><body><h1>No redux here</h1></body></html>"
    assert extract_seek_redux_data(raw_html) is None


def test_scrape_serp_http_parsing(monkeypatch):
    sample_html = """
    <html><script>
    window.SEEK_REDUX_DATA = {
        "results": {
            "results": {
                "jobs": [
                    {
                        "id": "99901",
                        "title": "Junior Backend Engineer",
                        "advertiser": {"description": "Tech Corp"},
                        "locations": [{"label": "Jakarta Raya"}],
                        "salary": "IDR 8.000.000 - 10.000.000",
                        "teaser": "Awesome tech job"
                    }
                ]
            }
        }
    };
    </script></html>
    """
    monkeypatch.setattr("src.scrape.fetch_http_page", lambda url: sample_html)
    cfg = {"search": {"base": "https://id.jobstreet.com"}}
    jobs = scrape_serp_http("https://id.jobstreet.com/id/jobs", cfg)
    assert jobs is not None
    assert len(jobs) == 1
    assert jobs[0]["jobstreet_id"] == "99901"
    assert jobs[0]["title"] == "Junior Backend Engineer"
    assert jobs[0]["company"] == "Tech Corp"
    assert jobs[0]["location"] == "Jakarta Raya"
    assert jobs[0]["salary_text"] == "IDR 8.000.000 - 10.000.000"


def test_scrape_detail_http_parsing(monkeypatch):
    sample_html = """
    <html><script>
    window.SEEK_REDUX_DATA = {
        "jobdetails": {
            "result": {
                "job": {
                    "id": "99901",
                    "title": "Junior Backend Engineer",
                    "advertiser": {"name": "Tech Corp"},
                    "location": {"label": "Jakarta Raya"},
                    "salary": "IDR 8M",
                    "content": "<p>We are hiring! <ul><li>Python</li></ul></p>",
                    "classifications": [{"label": "Information Technology"}],
                    "workTypes": {"label": "Full time"},
                    "isExpired": false
                }
            }
        }
    };
    </script></html>
    """
    monkeypatch.setattr("src.scrape.fetch_http_page", lambda url: sample_html)
    cfg = {"search": {"base": "https://id.jobstreet.com"}}
    job_card = {
        "jobstreet_id": "99901",
        "url": "https://id.jobstreet.com/id/job/99901",
        "title": "Old Title",
    }
    detail = scrape_detail_http(job_card, cfg)
    assert detail is not None
    assert detail["title"] == "Junior Backend Engineer"
    assert detail["company"] == "Tech Corp"
    assert "Python" in detail["description"]
    assert "Information Technology" in detail["teaser"]


def test_check_bot_wall_pauses_and_resumes(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from src.scrape import _check_bot_wall

    storage_file = tmp_path / "storage_state.json"
    monkeypatch.setattr("src.scrape.STORAGE_STATE_PATH", storage_file)

    mock_page = MagicMock()
    mock_page.url = "https://id.jobstreet.com/id/jobs"

    # 1st call: blocked with cloudflare/bot text
    # 2nd call: challenge cleared
    responses = ["Just a moment... Cloudflare verify you are human", "Normal job page content"]
    mock_page.locator.return_value.inner_text.side_effect = responses

    monkeypatch.setattr("time.sleep", lambda s: None)

    # Should not raise BotWallError because it cleared before timeout
    _check_bot_wall(mock_page, wait_timeout=10)
    assert mock_page.locator.call_count >= 2
    mock_page.context.storage_state.assert_called_once_with(path=str(storage_file))


def test_check_bot_wall_times_out(monkeypatch):
    import pytest
    from unittest.mock import MagicMock
    from src.scrape import _check_bot_wall, BotWallError

    mock_page = MagicMock()
    mock_page.url = "https://id.jobstreet.com/id/jobs"
    mock_page.locator.return_value.inner_text.return_value = "verify you are human"

    # Make time progress beyond timeout
    t = [0.0]
    def fake_time():
        t[0] += 5.0
        return t[0]
    monkeypatch.setattr("time.time", fake_time)
    monkeypatch.setattr("time.sleep", lambda s: None)

    with pytest.raises(BotWallError) as exc_info:
        _check_bot_wall(mock_page, wait_timeout=10)

    assert "challenge timed out" in str(exc_info.value)


def test_m11_scrape_detail_http_distinguishes_expired_from_parse_fail(monkeypatch):
    expired_html = """
    <html><script>
    window.SEEK_REDUX_DATA = {
        "jobdetails": {
            "result": {
                "job": {
                    "id": "99902",
                    "title": "Expired Job",
                    "isExpired": true
                }
            }
        }
    };
    </script></html>
    """
    monkeypatch.setattr("src.scrape.fetch_http_page", lambda url: expired_html)
    cfg = {"search": {"base": "https://id.jobstreet.com"}}
    job_card = {
        "jobstreet_id": "99902",
        "url": "https://id.jobstreet.com/id/job/99902",
    }
    # Expired job should return a dict with is_expired = True
    detail = scrape_detail_http(job_card, cfg)
    assert detail is not None
    assert detail.get("is_expired") is True

    # Failed parse / 404 should return None
    monkeypatch.setattr("src.scrape.fetch_http_page", lambda url: "<html>No data</html>")
    detail_fail = scrape_detail_http(job_card, cfg)
    assert detail_fail is None
