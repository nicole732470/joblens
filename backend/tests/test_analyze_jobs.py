"""Async analysis job reuse across Web and extension."""

from app import analyze_jobs


def test_equivalent_requests_reuse_job():
    key = "same-user-job-inputs"
    first, created_first = analyze_jobs.create_or_get_job(run_id="run-one", cache_key=key)
    second, created_second = analyze_jobs.create_or_get_job(run_id="run-two", cache_key=key)
    assert created_first is True
    assert created_second is False
    assert second == first


def test_failed_job_can_be_retried():
    key = "retry-after-failure"
    first, _ = analyze_jobs.create_or_get_job(run_id="run-fail", cache_key=key)
    analyze_jobs.fail_job(first, error="temporary failure")
    second, created = analyze_jobs.create_or_get_job(run_id="run-retry", cache_key=key)
    assert created is True
    assert second != first
