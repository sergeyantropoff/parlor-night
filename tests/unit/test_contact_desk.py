"""Текст формы обратной связи помечен и помещается в сообщение."""

from app.contact_desk import MARKER, feedback_text


def test_feedback_names_the_form_and_the_reply_mail() -> None:
    text = feedback_text("Анна", "anna@example.com", "гость не вошёл", "Не открывается вход.")
    assert text.startswith(MARKER)
    assert "только на почту" in text
    assert "anna@example.com" in text
    assert "Не открывается вход." in text
    assert len(text) <= 4500
