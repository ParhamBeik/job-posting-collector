"""Browser checks of page behaviour beyond XSS (Playwright, offline)."""

from conftest import MANY


def test_out_of_range_page_in_a_link_falls_back_to_the_last_page(page, server):
    page.goto(server + "/?page=999")
    page.locator("#results li").wait_for()
    assert page.locator("#showing").inner_text() == "Showing 1–1 of 1"
    assert "page=" not in page.url


def test_run_issues_list_every_item_and_fold_big_groups(page, server):
    page.goto(server)
    page.locator("#runs tr").first.click()
    group = page.locator("#run-issues details", has_text="FETCH_TIMEOUT")
    group.wait_for()
    assert group.locator("li").count() == MANY
    assert group.get_attribute("open") is None  # folded: more than 20
    assert page.locator("#run-issues details", has_text="FIELD_MISSING").get_attribute("open") is not None
