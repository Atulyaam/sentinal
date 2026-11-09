"""Secure request payload parsing for manual log file imports."""

import base64
import email
from email.policy import default
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("sentinel.upload")


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize filename to its safe basename, stripping any path traversal characters."""
    if not filename or not filename.strip():
        return "uploaded_file.log"
    # Extract only the final basename component across POSIX and Windows delimiters
    clean_base = Path(filename.replace("\\", "/")).name
    # Strip illegal characters and control bytes
    clean_name = re.sub(r'[\x00-\x1f/\\<>:"|?*]', "_", clean_base).strip(" ._")
    return clean_name or "uploaded_file.log"


def parse_import_payload(
    content_type_header: str,
    raw_body: bytes,
) -> Tuple[Optional[str], Optional[bytes], Optional[str], Optional[str], Optional[str]]:
    """Parse incoming import request body.

    Returns:
        (filename, content_bytes, parser_id, source_id, error_message)
    """
    content_type = content_type_header.lower()

    if "application/json" in content_type:
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            return None, None, None, None, f"Malformed JSON request body: {err}"

        if not isinstance(data, dict):
            return None, None, None, None, "Request JSON body must be an object."

        raw_filename = data.get("filename", "uploaded_file.log")
        filename = sanitize_filename(str(raw_filename))
        parser_id = str(data.get("parser_id", "generic_jsonl")).strip()
        source_id = str(data.get("source_id", "src_manual_default")).strip()

        if "content_bytes" in data and isinstance(data["content_bytes"], str):
            # Base64 encoded payload
            try:
                content = base64.b64decode(data["content_bytes"])
            except Exception as err:
                return None, None, None, None, f"Failed to decode base64 content: {err}"
        elif "content_text" in data and isinstance(data["content_text"], str):
            content = data["content_text"].encode("utf-8")
        elif "content" in data and isinstance(data["content"], str):
            content = data["content"].encode("utf-8")
        else:
            return None, None, None, None, "Missing file content in JSON body (expected 'content_text' or 'content_bytes')."

        return filename, content, parser_id, source_id, None

    if "multipart/form-data" in content_type:
        try:
            # Construct synthetic MIME message for standard email parser
            mime_bytes = b"Content-Type: " + content_type_header.encode("latin-1") + b"\r\n\r\n" + raw_body
            msg = email.message_from_bytes(mime_bytes, policy=default)

            if not msg.is_multipart():
                return None, None, None, None, "Malformed multipart request: missing boundary or parts."

            filename = None
            content = None
            parser_id = None
            source_id = "src_manual_default"

            for part in msg.iter_parts():
                disp = part.get_param("name", header="content-disposition")
                if not disp:
                    continue

                if disp == "file":
                    raw_fn = part.get_filename() or "uploaded_file.log"
                    filename = sanitize_filename(raw_fn)
                    content = part.get_payload(decode=True)
                elif disp == "parser_id":
                    payload_val = part.get_payload(decode=True)
                    if payload_val:
                        parser_id = payload_val.decode("utf-8", errors="replace").strip()
                elif disp == "source_id":
                    payload_val = part.get_payload(decode=True)
                    if payload_val:
                        source_id = payload_val.decode("utf-8", errors="replace").strip()

            if not content:
                return None, None, None, None, "Multipart form missing 'file' payload."

            if not parser_id:
                parser_id = "generic_jsonl"

            return filename, content, parser_id, source_id, None

        except Exception as err:
            logger.error("Multipart parsing failure: %s", err, exc_info=True)
            return None, None, None, None, f"Failed to parse multipart/form-data: {err}"

    return None, None, None, None, f"Unsupported Content-Type '{content_type_header}'. Use multipart/form-data or application/json."
