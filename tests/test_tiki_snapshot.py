from marketplacex import tiki


def test_clean_description():
    assert tiki.clean_description("<p>Hello&nbsp;<b>world</b></p>") == "Hello world"
    long = tiki.clean_description("<p>" + "a" * 400 + "</p>")
    assert len(long) == 255 and long.endswith("...")
    assert tiki.clean_description(None) == ""


def test_snapshot_has_50_plus_per_category():
    snap = tiki.load_snapshot()
    assert len(snap["categories"]) == 8
    for c in snap["categories"]:
        assert len(c["products"]) >= 50, c["name"]
        for p in c["products"]:
            assert p["price"] > 0 and p["images"] and all(len(u) <= 500 for u in p["images"])
            assert len(p["description"]) <= 255
