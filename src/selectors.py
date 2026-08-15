"""Centralized selectors. If Jobstreet changes its DOM, fixes happen here only.

All hooks verified live on id.jobstreet.com on 2026-08-15 (SEEK platform
`data-automation` test IDs).
"""


class SiteChangedError(RuntimeError):
    """A selector no longer matches — fail loudly, never guess."""


SERP_CARD = "article"
SERP_JOB_LINK = 'a[href*="/job/"]'
JOB_ID_RE = r"/job/(\d+)"

DETAIL_TITLE = '[data-automation="job-detail-title"]'
DETAIL_ADVERTISER = '[data-automation="advertiser-name"]'
DETAIL_LOCATION = '[data-automation="job-detail-location"]'
DETAIL_CLASSIFICATIONS = '[data-automation="job-detail-classifications"]'
DETAIL_WORK_TYPE = '[data-automation="job-detail-work-type"]'
DETAIL_SALARY = '[data-automation="job-detail-salary-match"]'
DETAIL_APPLY = '[data-automation="job-detail-apply"]'
DETAIL_DESCRIPTION = '[data-automation="jobAdDetails"]'
DETAIL_BADGES = '[data-automation="jdv-badges-section"]'

# Text fragments used to detect bot walls / session loss (fail-stop signals)
BOT_WALL_MARKERS = ("captcha", "verify you are human", "datadome", "are you a robot")
LOGIN_MARKERS = ("sign in to apply", "masuk untuk melamar")
