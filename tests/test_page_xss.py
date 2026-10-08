"""The one XSS browser test: scraped text shown on the page can never run as code (Playwright)."""


def test_malicious_posting_is_shown_as_text_and_never_runs(page, server):
    page.goto(server)
    title = page.locator("#results .title")
    title.wait_for()
    # The attack is visible as literal characters...
    assert "<img src=x onerror=window.__pwned=1>" in title.inner_text()
    title.click()
    page.locator("#detail:not([hidden])").wait_for()
    assert "<img src=x" in page.locator("#detail-title").inner_text()
    page.locator("#runs tr").first.click()
    issues = page.locator("#run-issues")
    issues.wait_for()
    assert "<img src=x onerror=window.__pwned=2>" in issues.inner_text()

    # ...and nothing from it became markup or ran.
    assert page.locator("main img").count() == 0
    assert page.locator("#run-issues details", has_text="FIELD_MISSING").locator("a").count() == 0
    assert page.locator("a[href^='javascript']").count() == 0  # the javascript: URL got no link
    assert page.evaluate("window.__pwned") is None
    assert page.locator("#detail-link").get_attribute("href").startswith("https://eng-estekhdam.com/")
    body = page.locator("#detail-body").inner_text()
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in body and "09120000000" not in body
