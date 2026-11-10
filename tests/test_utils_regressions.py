import unittest
from unittest.mock import MagicMock

from utils import markdown_to_text, send_rich_response, split_plain_text


class TestPlainResponseRegressions(unittest.TestCase):
    def test_plain_download_and_fallback_keep_fenced_code_indentation_and_blank_lines(self):
        code = "    first = 1\n\n\n    second = first * 2"
        self.assertEqual(markdown_to_text(f"```python\n{code}\n```"), code)

    def test_plain_download_keeps_link_destinations_without_duplicating_autolinks(self):
        source = "Источник: [документация](https://example.com/docs?q=1&lang=ru)"
        self.assertEqual(
            markdown_to_text(source),
            "Источник: документация (https://example.com/docs?q=1&lang=ru)",
        )
        self.assertEqual(markdown_to_text("<https://example.com>"), "https://example.com")

    def test_plain_split_preserves_literal_markdown_symbols_and_whitespace(self):
        text = ("    total = value * factor + `offset`\n\n" * 200).rstrip("\n")
        parts = split_plain_text(text)
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 4000 for part in parts))

    def test_rich_fallback_does_not_inject_formatting_characters_into_code(self):
        bot = MagicMock()
        bot.send_rich_message.side_effect = RuntimeError("Rich messages unavailable")
        code = ("    total = value * factor\n" * 250).rstrip("\n")
        sent = send_rich_response(bot, 123, f"```python\n{code}\n```", reply_to_message_id=42)
        chunks = [call.args[1] for call in bot.send_message.call_args_list]
        self.assertGreater(len(sent), 1)
        self.assertEqual("".join(chunks), code)
        self.assertEqual(bot.send_message.call_args_list[0].kwargs["reply_parameters"].message_id, 42)
        self.assertTrue(all(call.kwargs["reply_parameters"] is None
                            for call in bot.send_message.call_args_list[1:]))

    def test_rich_fallback_respects_unicode_limit_for_emoji(self):
        bot = MagicMock()
        bot.send_rich_message.side_effect = RuntimeError("Rich messages unavailable")
        text = "🎉" * 3000
        send_rich_response(bot, 123, text)
        chunks = [call.args[1] for call in bot.send_message.call_args_list]
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 <= 4000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
