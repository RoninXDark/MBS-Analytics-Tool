from bond_story_reporting.data.story_parser import parse_story_label


def test_parse_underscore_delimited_geo_symbol():
    parsed = parse_story_label("FNCI_1.5_2020_FL")

    assert parsed["program"] == "FNCI"
    assert parsed["coupon"] == 1.5
    assert parsed["origination_year"] == 2020
    assert parsed["geography"] == "FL"
    assert parsed["loan_balance_bucket"] is None
    assert parsed["story_family"] == "FNCI"
    assert parsed["story_tag"] is None
    assert parsed["parse_success"] is True


def test_parse_underscore_delimited_loan_balance_symbol():
    parsed = parse_story_label("FNCI_1.5_2020_LB110")

    assert parsed["program"] == "FNCI"
    assert parsed["coupon"] == 1.5
    assert parsed["origination_year"] == 2020
    assert parsed["geography"] is None
    assert parsed["loan_balance_bucket"] == "LB110"
    assert parsed["story_family"] == "FNCI"
    assert parsed["story_tag"] is None
    assert parsed["parse_success"] is True


def test_parse_underscore_delimited_story_tag_symbol():
    parsed = parse_story_label("FNCI_1.5_2020_FICO")

    assert parsed["program"] == "FNCI"
    assert parsed["coupon"] == 1.5
    assert parsed["origination_year"] == 2020
    assert parsed["geography"] is None
    assert parsed["loan_balance_bucket"] is None
    assert parsed["story_family"] == "FNCI"
    assert parsed["story_tag"] == "FICO"
    assert parsed["parse_success"] is True


def test_space_delimited_labels_still_parse():
    parsed = parse_story_label("2023 FNCL 5.0 NY LB125")

    assert parsed["program"] == "FNCL"
    assert parsed["coupon"] == 5.0
    assert parsed["origination_year"] == 2023
    assert parsed["geography"] == "NY"
    assert parsed["loan_balance_bucket"] == "LB125"
    assert parsed["story_family"] == "FNCL"
    assert parsed["parse_success"] is True
