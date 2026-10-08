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


def test_swapped_dates_are_fixed_instead_of_failing(page, server):
    page.goto(server + "/?date_from=2026-10-08&date_to=2026-10-01")
    page.locator("#results li").wait_for()
    assert page.locator("#search-error").is_hidden()
    assert page.input_value("[name=date_from]") == "2026-10-01" and page.input_value("[name=date_to]") == "2026-10-08"


def test_no_match_explains_itself_and_show_all_brings_everything_back(page, server):
    page.goto(server + "/?q=no-such-words-anywhere")
    page.locator("#empty").wait_for()
    assert "No postings match" in page.locator("#empty").inner_text()
    page.click("#show-all")
    page.locator("#results li").wait_for()
    assert page.locator("#empty").is_hidden() and "q=" not in page.url


def test_day_chart_has_a_tooltip_a_legend_and_a_table_view(page, server):
    page.goto(server)
    page.locator(".day").first.wait_for()
    assert page.locator(".day").count() == 7
    page.locator(".day[data-date='2026-10-07']").hover()
    tip = page.locator("#tooltip")
    tip.wait_for()
    assert "Civil & structures" in tip.inner_text() and "Total" in tip.inner_text()  # the seeded ad is tagged civil
    assert page.locator("#legend .legend-item").count() == 1
    page.click(".table-view summary")
    assert page.locator("#days-table tbody tr").count() == 7
