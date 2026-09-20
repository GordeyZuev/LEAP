"""Braces in exception text and log context must stay literal."""

import pytest

from logger import _file_format, get_logger


@pytest.mark.unit
def test_json_braces_in_logs_stay_literal() -> None:
    log = get_logger()
    captured: list[str] = []
    sink_id = log.add(captured.append, format=_file_format, catch=False)
    try:
        with log.contextualize(user_id='{"handler": "x"}'):
            log.error("stage failed")
            try:
                raise RuntimeError('{"handler": "captcha"}')
            except RuntimeError as exc:
                log.opt(exception=True).error(f"Error downloading: {exc!r}")
    finally:
        log.remove(sink_id)

    text = "\n".join(captured)
    assert "stage failed" in text
    assert "Error downloading" in text
    assert "handler" in text
