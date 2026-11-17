from app.games.service import page_links
from app.paging import list_href, read_page, window


def test_short_lists_show_every_page() -> None:
    assert page_links(1, 1) == [1]
    assert page_links(2, 5) == [1, 2, 3, 4, 5]


def test_window_clamps_and_slices() -> None:
    frame = window(list(range(25)), read_page("3"), 10)
    assert frame["items"] == list(range(20, 25))
    assert frame["page"] == 3
    assert frame["pages"] == 3
    assert list_href("/news", 1) == "/news"
    assert list_href("/news", 2) == "/news?page=2"
    assert read_page("abc") == 1


def test_long_lists_keep_the_edges_and_the_neighbours() -> None:
    assert page_links(1, 12) == [1, 2, None, 12]
    assert page_links(5, 12) == [1, None, 4, 5, 6, None, 12]
    assert page_links(12, 12) == [1, None, 11, 12]
