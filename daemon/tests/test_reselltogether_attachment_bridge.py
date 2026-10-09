import base64
import hashlib
import unittest
from synapse_daemon.reselltogether_attachment_bridge import (
    AttachmentBridgeError, ingest_reselltogether_attachment, prepare_attachment,
)
class AttachmentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.image = bytes.fromhex("ffd8ff") + b"example-original-photo"
    def test_original_roundtrip(self):
        calls = []
        def invoke(name, args):
            calls.append((name,args))
            return {"ok": True}
        result = ingest_reselltogether_attachment(filename="photo.jpg", mime="image/jpeg",
            original_bytes=self.image, workspace_id="private", invoke_mcp=invoke)
        self.assertEqual(calls[0][0], "ingest_chat_attachment")
        self.assertEqual(base64.b64decode(calls[0][1]["data_base64"]), self.image)
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.image).hexdigest())
    def test_traversal_rejected(self):
        with self.assertRaises(AttachmentBridgeError):
            prepare_attachment(filename="../photo.jpg", mime="image/jpeg", original_bytes=self.image)
    def test_wrong_hash_rejected(self):
        with self.assertRaises(AttachmentBridgeError):
            prepare_attachment(filename="photo.jpg", mime="image/jpeg", original_bytes=self.image, expected_sha256="0"*64)
    def test_wrong_type_rejected(self):
        with self.assertRaises(AttachmentBridgeError):
            prepare_attachment(filename="photo.png", mime="image/png", original_bytes=self.image)
    def test_empty_rejected(self):
        with self.assertRaises(AttachmentBridgeError):
            prepare_attachment(filename="photo.jpg", mime="image/jpeg", original_bytes=b"")
if __name__ == "__main__":
    unittest.main()
