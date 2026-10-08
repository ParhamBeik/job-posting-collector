"""High-level industry groups for the per-day chart, built only from the site's own field tags.

Each source maps its field-tag slugs to these groups (`Source.field_groups`). An ad with several
field tags is counted once, in the most specific group it has (PRIORITY), so a day's groups always
add up to that day's number of ads. An ad with no known field tag is "other".
"""

GROUPS = (  # (key, English label, Persian label); this order is also the colour order on the page
    ("civil", "Civil & structures", "عمران و سازه"),
    ("architecture", "Architecture", "معماری"),
    ("surveying", "Surveying", "نقشه‌برداری"),
    ("transport", "Roads, rail & transport", "راه و حمل‌ونقل"),
    ("water", "Water & environment", "آب و محیط زیست"),
    ("management", "Construction management", "مدیریت ساخت"),
    ("other", "Other", "سایر"),
)
# Most specific first; "civil" is the site's broadest tag (on about 2 of 3 ads), so it comes last.
PRIORITY = ("surveying", "architecture", "transport", "water", "management", "civil")


def primary_group(field_slugs, mapping: dict[str, str]) -> str:
    groups = {mapping.get(slug) for slug in field_slugs}
    return next((group for group in PRIORITY if group in groups), "other")
