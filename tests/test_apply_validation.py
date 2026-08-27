"""Regression tests for the apply wizard's post-advance validation check.

JobStreet's Profile Updates step renders a static informational notice that
matches the error-banner selectors used by ``_check_step_errors``. Treating it
as fatal aborts every application right after the questionnaire step. The check
must only be fatal when the wizard did not actually advance to another step.
"""
import pytest

from src.apply import ApplyFailed, _step_signature, apply_to_job

PROFILE_NOTICE = (
    "Profil Jobstreet kamu adalah bagian dari lamaran kamu. "
    "Pastikan profil kamu sudah diperbarui."
)

JOB = {
    "jobstreet_id": "12345",
    "title": "Facilities Manager",
    "company": "PT Test",
    "url": "https://id.jobstreet.com/id/apply/12345/questions",
    "description": "",
}
PROFILE = {"salary": {"min_acceptable": 6000000, "preferred": 7000000}}


class FakeLocator:
    """Locator stand-in. The review submit button is visible only on the review URL."""

    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.is_visible() else 0

    def is_visible(self):
        if any(k in self._selector for k in ("review-submit-application", "Kirim lamaran", "Submit application")):
            return "/review" in self._page.url
        return False

    def click(self, *args, **kwargs):
        pass


class FakePage:
    def __init__(self, url):
        self.url = url

    def goto(self, url, **kwargs):
        self.url = url

    def locator(self, selector):
        return FakeLocator(self, selector)

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def wait_for_timeout(self, *args, **kwargs):
        pass


@pytest.fixture
def patched(monkeypatch):
    """Stubs out everything around the step loop; returns the screenshot call list."""
    monkeypatch.setattr("src.apply._click_apply", lambda page: None)
    monkeypatch.setattr("src.apply._check_bot_wall", lambda page: None)
    monkeypatch.setattr("src.apply._check_auth_state", lambda page: None)
    monkeypatch.setattr("src.apply._check_external_ats", lambda page, cfg: None)
    monkeypatch.setattr("src.apply._fill_known_fields", lambda *a, **k: [])
    shots = []
    monkeypatch.setattr("src.apply._screenshot", lambda page, tag: shots.append(tag))
    return shots


def _apply(page):
    return apply_to_job(
        page, JOB, {}, PROFILE, [],
        execute=False, use_llm_letter=False, interactive=False,
    )


def test_informational_notice_on_next_step_does_not_abort(patched, monkeypatch):
    """The exact failure from run #11: profile notice must not kill the application."""
    page = FakePage(JOB["url"])
    monkeypatch.setattr("src.apply._step_signature", lambda p: p.url)
    # The notice banner is present on every post-advance check.
    monkeypatch.setattr("src.apply._check_step_errors", lambda p: [PROFILE_NOTICE])

    next_urls = iter([
        "https://id.jobstreet.com/id/apply/12345/profile",
        "https://id.jobstreet.com/id/apply/12345/review",
    ])

    def advance(p):
        p.url = next(next_urls)
        return True

    monkeypatch.setattr("src.apply._click_continue_if_present", advance)

    result = _apply(page)
    assert result["status"] == "dry-run"
    assert patched == ["dryrun-12345"]  # dry-run proof shot only, no failure shot


def test_validation_failure_when_stuck_aborts(patched, monkeypatch):
    """Continue was clicked but the wizard did not advance: real validation error."""
    page = FakePage(JOB["url"])
    monkeypatch.setattr("src.apply._step_signature", lambda p: p.url)
    monkeypatch.setattr("src.apply._check_step_errors", lambda p: ["Pertanyaan ini wajib diisi"])
    monkeypatch.setattr("src.apply._click_continue_if_present", lambda p: True)

    with pytest.raises(ApplyFailed, match="validation errors on step 1"):
        _apply(page)
    assert patched == ["val-error-12345"]


def test_unreadable_signature_keeps_errors_fatal(patched, monkeypatch):
    """When the step cannot be identified, errors must remain fatal (no silent pass)."""
    page = FakePage(JOB["url"])
    monkeypatch.setattr("src.apply._step_signature", lambda p: "")
    monkeypatch.setattr("src.apply._check_step_errors", lambda p: ["Some error banner"])
    monkeypatch.setattr("src.apply._click_continue_if_present", lambda p: True)

    with pytest.raises(ApplyFailed, match="validation errors"):
        _apply(page)


def test_step_signature_contract():
    class GoodPage:
        def evaluate(self, *args, **kwargs):
            return "/apply/123/profile|Profile Updates"

    class NullPage:
        def evaluate(self, *args, **kwargs):
            return None

    class BrokenPage:
        def evaluate(self, *args, **kwargs):
            raise RuntimeError("page closed")

    assert _step_signature(GoodPage()) == "/apply/123/profile|Profile Updates"
    assert _step_signature(NullPage()) == ""
    assert _step_signature(BrokenPage()) == ""
