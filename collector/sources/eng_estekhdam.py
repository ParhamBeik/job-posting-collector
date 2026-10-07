"""Adapter for eng-estekhdam.com (WordPress, "typology" theme).

Elements are chosen by meaning (post-ID class, rel="tag", the date element), never by
position. Everything read here is untrusted: only plain text leaves this module, and only
http(s) URLs on the source host are accepted.
"""

import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag as Element

from collector.dates import DateParseError, jalali_to_gregorian, parse_jalali_date
from collector.normalize import normalize
from collector.models import Issue, ListingItem, Posting, Tag

BASE = "https://eng-estekhdam.com"
HOST = "eng-estekhdam.com"
POSTING_PATH = re.compile(r"^/(\d{4})/(\d{2})/(\d{2})/[^/]+/$")  # /1405/07/15/<slug>/
POST_ID_CLASS = re.compile(r"^post-(\d+)$")

# Removed from the posting body before reading text: active content, the "report this ad"
# widget, the members-only block (contact details), the tag links, and hidden elements.
NOT_BODY = (
    "script, style, iframe, noscript, object, embed, form, button, template, "
    ".wprc-container, .rcp_restricted, .entry-tags, "
    "[hidden], [aria-hidden=true], [style*='display:none'], [style*='display: none']"
)
BLOCKS = ["p", "div", "li", "ol", "ul", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "tr"]
SHORT_BODY = 40
CHALLENGE_WORDS = ("bitninja", "captcha", "checking your browser", "security check")


class _Reject(Exception):
    """Internal: stops reading one record and carries the issue to report."""

    def __init__(self, issue: Issue):
        self.issue = issue


def _text(element: Element | None) -> str:
    return " ".join(element.get_text(" ").split()) if element else ""


def _body_text(content: Element) -> str:
    for element in content.select(NOT_BODY):
        element.decompose()
    for br in content.find_all("br"):
        br.replace_with("\n")
    for item in content.find_all("li"):
        item.insert(0, "- ")
    for block in content.find_all(BLOCKS):
        block.insert_before("\n")
        block.insert_after("\n")
    lines = (" ".join(line.split()) for line in content.get_text().splitlines())
    return "\n".join(line for line in lines if line)


def _slug(href: str, kind: str) -> str | None:
    try:
        path = urlsplit(href).path
    except ValueError:  # malformed URL in untrusted HTML: no tag rather than a crash
        return None
    match = re.search(rf"/{kind}/([^/]+)/?$", path)
    return unquote(match.group(1)) if match else None


class EngEstekhdam:
    name = "eng-estekhdam"
    parser_version = "eng-estekhdam/1"

    def listing_url(self, page: int) -> str:
        return f"{BASE}/" if page == 1 else f"{BASE}/page/{page}/"

    def check_page(self, html: str, kind: str) -> str | None:
        soup = BeautifulSoup(html, "lxml")
        body = set(soup.body.get("class", [])) if soup.body else set()
        if kind == "listing" and "home" in body and soup.select_one(".typology-section"):
            return None
        if kind == "posting" and "single-post" in body and soup.select_one("article.typology-single-post"):
            return None
        # Real pages load a reCAPTCHA script, so only a page without the site's own theme frame
        # whose *visible* text talks about a browser check counts as a firewall challenge.
        if "wp-theme-typology" not in body:
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            visible = soup.get_text(" ").lower()
            if any(word in visible for word in CHALLENGE_WORDS):
                return "BLOCKED_CHALLENGE"
        if soup.select_one("form#loginform, form#rcp_login_form, form.rcp_form"):
            return "LOGIN_REQUIRED"
        return "LAYOUT_UNRECOGNIZED"

    def parse_listing(self, html: str) -> tuple[list[ListingItem], list[Issue]]:
        items, issues = [], []
        for article in BeautifulSoup(html, "lxml").select("article.typology-post"):
            try:
                item, warnings = self._card(article)
            except _Reject as reject:
                issues.append(reject.issue)
            else:
                items.append(item)
                issues += warnings
        return items, issues

    def parse_posting(self, html: str, item: ListingItem) -> tuple[Posting | None, list[Issue]]:
        try:
            return self._posting(html, item)
        except _Reject as reject:
            return None, [reject.issue]

    def _card(self, article: Element) -> tuple[ListingItem, list[Issue]]:
        classes = article.get("class", [])
        ids = [m.group(1) for c in classes if (m := POST_ID_CLASS.match(c))]
        anchor = article.select_one(".entry-title a")
        url = (anchor.get("href") or "").strip() if anchor else ""
        if not ids:
            raise _Reject(Issue.error("FIELD_MISSING", "card has no post id", url or None))
        post_id = ids[0]
        if not url:
            raise _Reject(Issue.error("FIELD_MISSING", f"post {post_id}: no link"))
        url_day = self._url_day(url, post_id)
        title = _text(anchor)
        if not title:
            raise _Reject(Issue.error("FIELD_MISSING", f"post {post_id}: no title", url))
        warnings = []
        date_text = _text(article.select_one(".post-date-hidden"))
        if not date_text:
            # The URL date is already validated, and the posting page date is checked against it
            # later, so the record keeps two independent date sources. Never silent.
            warnings.append(Issue.warning("FALLBACK_USED", f"post {post_id}: no card date, using URL date", url))
            day = url_day
        else:
            try:
                day = parse_jalali_date(date_text)
            except DateParseError as error:
                raise _Reject(Issue.error("DATE_UNPARSEABLE", f"post {post_id}: {error}", url)) from None
        if day != url_day:
            raise _Reject(
                Issue.error("DATE_MISMATCH", f"post {post_id}: card {day}, URL {url_day}", url)
            )
        tags = tuple(
            Tag("province", c.removeprefix("category-")) if c.startswith("category-")
            else Tag("field", c.removeprefix("tag-"))
            for c in classes
            if c.startswith(("category-", "tag-"))
        )
        return ListingItem(post_id, url, title, day, tags), warnings

    def _url_day(self, url: str, post_id: str):
        """Only http(s) posting URLs on the source host; returns the Jalali date in the path."""
        try:
            parts = urlsplit(url)
        except ValueError:  # e.g. "http://[::1/…": one bad link must not crash the whole page
            parts = None
        match = parts and POSTING_PATH.match(parts.path)
        # Exact host: no port, no user info, no look-alikes.
        if not parts or parts.scheme not in ("http", "https") or parts.netloc != HOST or not match:
            raise _Reject(Issue.error("URL_REJECTED", f"post {post_id}: not a source posting URL: {url!r}"))
        try:
            return jalali_to_gregorian(*(int(part) for part in match.groups()))
        except DateParseError as error:
            raise _Reject(Issue.error("DATE_UNPARSEABLE", f"post {post_id}: URL {error}", url)) from None

    def _posting(self, html: str, item: ListingItem) -> tuple[Posting, list[Issue]]:
        url, post_id = item.url, item.source_post_id
        main = BeautifulSoup(html, "lxml").select_one("article.typology-single-post")
        if main is None:
            raise _Reject(Issue.error("LAYOUT_UNRECOGNIZED", f"post {post_id}: no main posting", url))
        if f"post-{post_id}" not in main.get("class", []):
            raise _Reject(Issue.error("ID_MISMATCH", f"page is not post {post_id}", url))

        date_text = _text(main.select_one(".entry-header .meta-date"))
        if not date_text:
            raise _Reject(Issue.error("FIELD_MISSING", f"post {post_id}: no date on posting page", url))
        try:
            day = parse_jalali_date(date_text)
        except DateParseError as error:
            raise _Reject(Issue.error("DATE_UNPARSEABLE", f"post {post_id}: {error}", url)) from None
        if day != item.published_date:
            raise _Reject(
                Issue.error("DATE_MISMATCH", f"post {post_id}: page {day}, card {item.published_date}", url)
            )

        title = _text(main.select_one("h1.entry-title"))
        if not title:
            raise _Reject(Issue.error("FIELD_MISSING", f"post {post_id}: no title on posting page", url))

        tags = tuple(
            Tag(kind, slug, _text(link))
            for kind, selector in (("province", ".meta-category a[href]"), ("field", ".entry-tags a[href]"))
            for link in main.select(selector)
            if (slug := _slug(link["href"], "category" if kind == "province" else "tag"))
        )

        content = main.select_one(".entry-content")
        members_only = bool(content and content.select_one(".rcp_restricted"))
        body = _body_text(content) if content else ""
        if not body:
            raise _Reject(Issue.error("FIELD_MISSING", f"post {post_id}: empty body", url))

        warnings = []
        if normalize(title) != normalize(item.title):
            warnings.append(Issue.warning("TITLE_MISMATCH", f"post {post_id}: listing and posting titles differ", url))
        if {(t.kind, t.slug) for t in tags} != {(t.kind, t.slug) for t in item.tags}:
            warnings.append(Issue.warning("TAGS_MISMATCH", f"post {post_id}: listing and posting tags differ", url))
        if len(body) < SHORT_BODY:
            warnings.append(Issue.warning("BODY_SHORT", f"post {post_id}: body has {len(body)} characters", url))
        posting = Posting(self.name, post_id, url, title, body, day, tags, self.parser_version, members_only)
        return posting, warnings
