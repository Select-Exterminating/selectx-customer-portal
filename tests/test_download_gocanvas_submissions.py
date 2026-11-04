import importlib.util
from pathlib import Path

import httpx
import pytest

_path = Path(__file__).parent.parent / "scripts" / "download_gocanvas_submissions.py"
_spec = importlib.util.spec_from_file_location("download_gocanvas_submissions", _path)
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def _client(pages: dict[int, object], requests: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(dict(request.url.params))
        return httpx.Response(200, json=pages[int(request.url.params["page"])])

    return httpx.Client(base_url="https://gocanvas.test", transport=httpx.MockTransport(handler))


def test_lists_every_page_until_one_comes_back_empty():
    requests: list = []
    pages = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 2}, {"id": 3}], 3: []}
    assert script.list_submission_ids(_client(pages, requests), 5777327, 1) == [1, 2, 3]
    assert requests == [{"form_id": "5777327", "page": str(n)} for n in (1, 2, 3)]


def test_a_page_that_repeats_stops_instead_of_looping_forever():
    pages = {1: [{"id": 1}], 2: [{"id": 1}]}
    with pytest.raises(RuntimeError, match="isn't advancing"):
        script.list_submission_ids(_client(pages), 5777327, 1)


@pytest.mark.parametrize("page", [{"submissions": []}, [{"name": "no id"}]])
def test_an_unexpected_page_is_an_error(page):
    with pytest.raises(RuntimeError, match="page 1"):
        script.list_submission_ids(_client({1: page}), 5777327, 1)
