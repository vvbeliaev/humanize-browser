from humanize_browser.snapshot import walk_tree, build_ref_locator_args, format_snapshot


def make_tree():
    return {
        "role": "RootWebArea",
        "name": "Test Page",
        "children": [
            {"role": "heading", "name": "Hello World", "level": 1},
            {"role": "link", "name": "Click me"},
            {"role": "button", "name": "Submit"},
            {"role": "link", "name": "Click me"},  # duplicate
        ],
    }


def test_walk_tree_assigns_refs():
    lines, ref_map = walk_tree(make_tree())
    assert "@e1" in ref_map
    assert "@e2" in ref_map
    assert "@e3" in ref_map
    assert "@e4" in ref_map
    assert len(ref_map) == 4


def test_walk_tree_formats_output():
    lines, _ = walk_tree(make_tree())
    text = "\n".join(lines)
    assert 'heading "Hello World" @e1' in text
    assert 'link "Click me" @e2' in text
    assert 'button "Submit" @e3' in text


def test_walk_tree_tracks_duplicates():
    _, ref_map = walk_tree(make_tree())
    assert ref_map["@e2"] == ("link", "Click me", 0)
    assert ref_map["@e4"] == ("link", "Click me", 1)


def test_build_ref_locator_args():
    args = build_ref_locator_args("button", "Submit", 0)
    assert args == {"role": "button", "name": "Submit", "nth": 0}


def test_format_snapshot_adds_numbering():
    lines = ['heading "Hello" @e1', 'link "Go" @e2']
    out = format_snapshot(lines)
    assert out == '[1] heading "Hello" @e1\n[2] link "Go" @e2'


def test_empty_tree():
    lines, ref_map = walk_tree({"role": "RootWebArea", "name": ""})
    assert lines == []
    assert ref_map == {}
