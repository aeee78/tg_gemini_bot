import base64
import io
import json
import unittest

from google.genai import types
from PIL import Image

from chat_context import portable_history, serialize_history, context_contents


class TestChatContext(unittest.TestCase):
    def test_model_switch_keeps_text_and_images_without_reusing_thought_signatures(self):
        history = [
            types.Content(role='user', parts=[types.Part.from_text(text='Remember this')]),
            types.Content(role='model', parts=[
                types.Part(text='private reasoning', thought=True),
                types.Part(text='Answer', thought_signature=b'model-specific'),
                types.Part.from_bytes(data=b'image', mime_type='image/png'),
            ]),
        ]
        portable = portable_history(history)
        self.assertEqual(portable[1].parts[0].text, 'Answer')
        self.assertIsNone(portable[1].parts[0].thought_signature)
        self.assertEqual(portable[1].parts[1].inline_data.data, b'image')
        self.assertEqual(history[1].parts[1].thought_signature, b'model-specific')
        data = json.loads(serialize_history(portable))
        self.assertEqual(base64.b64decode(data[1]['parts'][1]['inline_data']['data']), b'image')

    def test_context_snapshot_contains_pending_files_text_and_photos(self):
        history = [types.Content(role='user', parts=[types.Part(text='history')])]
        image = Image.new('RGB', (1, 1))
        contents = context_contents(history,
            [dict(data=b'file', mime_type='text/plain', filename='file.txt', caption='caption')],
            [dict(type='text', content='buffer text'), dict(type='photo', image=image, caption='photo caption'),
             dict(type='document', data=b'pdf', mime_type='application/pdf', filename='x.pdf')])
        self.assertEqual(len(contents), 2)
        self.assertEqual(len(history), 1)
        texts = [part.text for part in contents[1].parts if part.text]
        self.assertIn('buffer text', texts)
        self.assertIn('photo caption', texts)
        blobs = [part.inline_data for part in contents[1].parts if part.inline_data]
        self.assertEqual([blob.mime_type for blob in blobs], ['text/plain', 'image/png', 'application/pdf'])
        Image.open(io.BytesIO(blobs[1].data)).verify()


if __name__ == '__main__':
    unittest.main()
