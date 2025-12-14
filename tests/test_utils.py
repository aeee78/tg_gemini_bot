
import unittest
from app.utils.text import markdown_to_text, split_long_message

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

    def test_split_long_message(self):
        msg = "Short message"
        parts = split_long_message(msg, max_length=100)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0], msg)

        long_msg = "Para 1\n\nPara 2"
        # Force split
        parts = split_long_message(long_msg, max_length=10)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "Para 1\n\n")
        self.assertEqual(parts[1], "Para 2\n\n")

if __name__ == "__main__":
    unittest.main()
