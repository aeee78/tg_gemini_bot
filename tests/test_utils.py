import unittest
from unittest.mock import MagicMock
from telebot.types import InputRichMessage, ReplyParameters
from utils import (
    get_closers_and_openers,
    markdown_to_text,
    parse_markdown_state,
    send_rich_response,
    split_long_message,
)


class TestUtils(unittest.TestCase):
    def test_markdown_to_text_basic(self):
        self.assertEqual(markdown_to_text("Hello"), "Hello")
        self.assertEqual(markdown_to_text("**Bold**"), "Bold")
        self.assertEqual(markdown_to_text("*Italic*"), "Italic")

    def test_markdown_to_text_inline(self):
        # Regression test for inline formatting
        text = markdown_to_text("A **B** C")
        # Should be "A B C", not "A \nB\n C"
        self.assertEqual(text.strip(), "A B C")

    def test_markdown_to_text_paragraphs(self):
        text = markdown_to_text("Para 1\n\nPara 2")
        self.assertIn("Para 1", text)
        self.assertIn("Para 2", text)
        # Check that they are separated by newlines
        self.assertTrue("\n" in text)

    def test_markdown_to_text_br(self):
        # Case 1: Markdown double space
        text = markdown_to_text("Line 1  \nLine 2")
        self.assertIn("Line 1", text)
        self.assertIn("Line 2", text)
        self.assertNotIn("Line 1Line 2", text)

        # Case 2: Explicit <br>
        text_br = markdown_to_text("Line 1<br>Line 2")
        self.assertIn("Line 1", text_br)
        self.assertIn("Line 2", text_br)
        self.assertNotIn("Line 1Line 2", text_br)

    def test_markdown_to_text_list(self):
        text = markdown_to_text("- Item 1\n- Item 2")
        self.assertIn("Item 1", text)
        self.assertIn("Item 2", text)
        self.assertTrue("\n" in text)

    def test_split_long_message_basic(self):
        msg = "Short message"
        parts = split_long_message(msg, max_length=100)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0], msg)

        long_msg = "Para 1\n\nPara 2"
        parts = split_long_message(long_msg, max_length=10)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "Para 1")
        self.assertEqual(parts[1], "Para 2")

    def test_split_long_message_bold_balance(self):
        text = "**" + "A" * 40 + " " + "B" * 40 + "**"
        parts = split_long_message(text, max_length=60)
        self.assertGreater(len(parts), 1)
        # First part should close with **
        self.assertTrue(parts[0].endswith("**"))
        # Second part should start with **
        self.assertTrue(parts[1].startswith("**"))

    def test_split_long_message_code_block_balance(self):
        text = "```python\ndef foo():\n" + "    x = 1\n" * 6 + "```"
        parts = split_long_message(text, max_length=60)
        self.assertGreater(len(parts), 1)
        # First part should close code block
        self.assertTrue(parts[0].endswith("```"))
        # Second part should reopen code block with python
        self.assertTrue(parts[1].startswith("```python\n"))

    def test_parse_markdown_state(self):
        state = parse_markdown_state("```python\ndef foo():\n**bar")
        self.assertTrue(state["in_code_block"])
        self.assertEqual(state["code_block_lang"], "python")

        state2 = parse_markdown_state("**bold** and *italic")
        self.assertFalse(state2["in_bold"])
        self.assertTrue(state2["in_italic"])

    def test_send_rich_response_basic(self):
        mock_bot = MagicMock()
        mock_bot.send_rich_message.return_value = "msg_obj"

        markdown_text = "# Header\n\n| Col 1 | Col 2 |\n|---|---|\n| A | B |"
        result = send_rich_response(
            bot=mock_bot,
            chat_id=123,
            markdown_text=markdown_text,
            reply_to_message_id=456,
        )

        self.assertEqual(result, ["msg_obj"])
        mock_bot.send_rich_message.assert_called_once()
        call_kwargs = mock_bot.send_rich_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], 123)
        self.assertIsInstance(call_kwargs["rich_message"], InputRichMessage)
        self.assertEqual(call_kwargs["rich_message"].markdown, markdown_text)
        self.assertIsInstance(call_kwargs["reply_parameters"], ReplyParameters)
        self.assertEqual(call_kwargs["reply_parameters"].message_id, 456)

    def test_send_rich_response_empty(self):
        mock_bot = MagicMock()
        result = send_rich_response(mock_bot, 123, "")
        self.assertEqual(result, [])
        mock_bot.send_rich_message.assert_not_called()

    def test_send_rich_response_fallback(self):
        mock_bot = MagicMock()
        mock_bot.send_rich_message.side_effect = Exception("Telegram API parse error")
        mock_bot.send_message.return_value = "fallback_msg"

        markdown_text = "**Bold** and *Italic*"
        result = send_rich_response(
            bot=mock_bot,
            chat_id=123,
            markdown_text=markdown_text,
        )

        self.assertEqual(result, ["fallback_msg"])
        mock_bot.send_rich_message.assert_called_once()
        mock_bot.send_message.assert_called_once()
        # Verify fallback stripped markdown
        args, kwargs = mock_bot.send_message.call_args
        self.assertEqual(args[0], 123)
        self.assertEqual(args[1], "Bold and Italic")

    def test_send_rich_response_long_message(self):
        mock_bot = MagicMock()
        mock_bot.send_rich_message.return_value = "msg_obj"
        mock_bot.send_message.return_value = "notice_msg"

        # Create message > 16000 chars
        paragraph = "A" * 10000 + "\n\n"
        long_markdown = paragraph + paragraph
        keyboard = MagicMock()

        result = send_rich_response(
            bot=mock_bot,
            chat_id=123,
            markdown_text=long_markdown,
            fallback_download_keyboard=keyboard,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_bot.send_rich_message.call_count, 2)
        # Should have sent notification about split
        mock_bot.send_message.assert_called_once_with(
            123,
            "Ответ был разбит на несколько сообщений.",
            reply_markup=keyboard,
        )


    def test_send_rich_response_fallback_long_message(self):
        mock_bot = MagicMock()
        mock_bot.send_rich_message.side_effect = Exception("RICH_MESSAGE_BLOCKS_TOO_MANY")
        mock_bot.send_message.return_value = "fallback_msg"

        # Create text > 4000 chars that fails rich message
        paragraph = ("Word " * 100 + "\n\n") * 15  # ~9000 chars
        keyboard = MagicMock()

        result = send_rich_response(
            bot=mock_bot,
            chat_id=123,
            markdown_text=paragraph,
            fallback_download_keyboard=keyboard,
        )

        # Should split into multiple fallback chunks of <= 4000 chars
        self.assertGreater(len(result), 1)
        self.assertGreater(mock_bot.send_message.call_count, 1)


if __name__ == "__main__":
    unittest.main()

