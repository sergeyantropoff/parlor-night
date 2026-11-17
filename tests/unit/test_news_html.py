from app.news_html import sanitize_news, visible_text


def test_plain_text_becomes_paragraphs() -> None:
    assert sanitize_news("Первая строка\n\nВторая") == "<p>Первая строка</p><p>Вторая</p>"


def test_script_and_handlers_are_removed() -> None:
    raw = '<p onclick="alert(1)">Вечер</p><script>alert(1)</script>'
    cleaned = sanitize_news(raw)
    assert cleaned == "<p>Вечер</p>"
    assert "script" not in cleaned
    assert "onclick" not in cleaned


def test_only_uploaded_images_remain() -> None:
    name = "a" * 32
    kept = sanitize_news(f'<img src="/news-images/{name}.png" alt="Вечер" onclick="alert(1)">')
    assert kept == f'<img src="/news-images/{name}.png" alt="Вечер">'
    assert "onclick" not in kept
    dropped = sanitize_news('<img src="https://evil.example/a.png" alt="чужая">')
    assert "<img" not in dropped
    raw = '<a href="javascript:alert(1)">плохо</a> <a href="https://parlor.example/news">хорошо</a>'
    cleaned = sanitize_news(raw)
    assert "javascript" not in cleaned
    assert 'href="https://parlor.example/news"' in cleaned
    assert visible_text(cleaned) == "плохо хорошо"
