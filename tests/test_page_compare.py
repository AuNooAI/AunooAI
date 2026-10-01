"""Work package 13: block comparison and content validation for vendor pages.

Pure functions, no network, no database. The same file lives in the SaaS
tree because page_compare.py is identical there.
"""

from app.collectors.page_compare import (
    NORMALIZER_VERSION,
    Block,
    K_LIST,
    K_TABLE,
    compare_blocks,
    extract_blocks,
    semantic_digest,
    validate_content,
)


def _cmp(old: str, new: str) -> dict:
    return compare_blocks(extract_blocks(old), extract_blocks(new))


def test_normalizer_version_is_set():
    assert NORMALIZER_VERSION == "2026.10.01-1"


def test_two_lines_versus_one_line_is_reflow_not_change():
    diff = _cmp("Starter $10\nPro $60", "Starter $10 Pro $60")
    assert diff["material"] is False
    assert diff["added"] == [] and diff["removed"] == []
    assert diff["reflowed_count"] > 0


def test_rewrapped_paragraph_hashes_the_same():
    a = ("The quick brown fox jumps over the lazy dog and keeps running through the\n"
         "field until dusk.")
    b = ("The quick brown fox jumps over the lazy dog and keeps\n"
         "running through the field until dusk.")
    assert extract_blocks(a) == extract_blocks(b)
    assert semantic_digest(extract_blocks(a)) == semantic_digest(extract_blocks(b))


def test_reordered_blocks_are_not_material():
    diff = _cmp("A\nB\nC", "C\nA\nB")
    assert diff["material"] is False
    assert diff["moved_count"] >= 1
    assert diff["added"] == [] and diff["removed"] == []


def test_price_change_is_material():
    diff = _cmp("Starter $10\nPro $60", "Starter $10\nPro $70")
    assert diff["material"] is True
    assert diff["added"] == ["Pro $70"]
    assert diff["removed"] == ["Pro $60"]


def test_duplicate_price_row_is_one_addition():
    old = "| Starter | $10 |\n| Pro | $60 |"
    new = old + "\n| Pro | $60 |"
    diff = _cmp(old, new)
    assert diff["material"] is True
    assert diff["added_count"] == 1
    assert diff["removed_count"] == 0
    assert diff["added"] == ["| Pro | $60 |"]


def test_removed_tier_is_material():
    diff = _cmp("Starter $10\nPro $60\nEnterprise $200", "Starter $10\nPro $60")
    assert diff["material"] is True
    assert diff["removed"] == ["Enterprise $200"]
    assert diff["added"] == []


def test_list_items_and_table_rows_keep_their_boundaries():
    blocks = extract_blocks("- apples\n- pears\n| a | b |\nplain text")
    assert [b.kind for b in blocks] == [K_LIST, K_LIST, K_TABLE, "text"]
    assert isinstance(blocks[0], Block)


def test_numbers_currency_and_units_are_untouched():
    blocks = extract_blocks("Price: €1,299.00 per month\n10 GB included")
    assert "€1,299.00" in blocks[0]
    assert blocks[1] == "10 GB included"


def test_whitespace_inside_a_line_is_collapsed():
    assert extract_blocks("Pro   $60\t\tmonthly") == ["Pro $60 monthly"]


def test_reflow_never_hides_a_changed_number():
    diff = _cmp("Starter $10\nPro $60", "Starter $10 Pro $70")
    assert diff["material"] is True


def test_challenge_page_with_200_is_blocked():
    outcome, reason = validate_content("Verify you are human", status=200)
    assert outcome == "blocked"
    assert reason


def test_cloudflare_just_a_moment_is_blocked():
    assert validate_content("Just a moment...", status=200)[0] == "blocked"


def test_blocking_status_is_blocked_regardless_of_text():
    assert validate_content("x" * 1000, status=403)[0] == "blocked"


def test_empty_text_is_extraction_failed():
    assert validate_content("")[0] == "extraction_failed"
    assert validate_content(None)[0] == "extraction_failed"
    assert validate_content("short")[0] == "extraction_failed"


def test_concise_page_is_ok():
    assert validate_content("x" * 500) == ("ok", "")


def test_long_page_mentioning_sign_in_is_ok():
    text = ("Our pricing is simple. " * 20) + " Sign in to manage your plan."
    assert len(text) >= 400
    assert validate_content(text)[0] == "ok"


def test_seventy_percent_drop_is_suspicious():
    outcome, reason = validate_content("y" * 250, prior_text="x" * 1000)
    assert outcome == "suspicious_drop"
    assert "1000" in reason and "250" in reason


def test_modest_shrink_is_ok():
    assert validate_content("y" * 600, prior_text="x" * 1000)[0] == "ok"


def test_blocked_wins_over_suspicious_drop():
    outcome, _ = validate_content("Access denied", prior_text="x" * 1000)
    assert outcome == "blocked"
