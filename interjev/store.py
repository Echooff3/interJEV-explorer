"""In-memory memory of the imagined internet.

Pages are cached so Back/Forward show the same thing, and each site keeps a
few notes (search snippet, pages seen, stylesheet) so JEV keeps it consistent.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass
class Site:
    notes: list[str] = field(default_factory=list)
    pages: "OrderedDict[str, str]" = field(default_factory=OrderedDict)  # path -> title
    stylesheet: str = ""
    identity: dict = field(default_factory=dict)  # JEV's identity answers, set by the first page


class Store:
    def __init__(self, max_pages: int = 500, pages_per_site: int = 20):
        self._lock = threading.Lock()
        self._pages: "OrderedDict[str, str]" = OrderedDict()
        self._sites: dict[str, Site] = {}
        self.max_pages = max_pages
        self.pages_per_site = pages_per_site

    def get_page(self, url: str) -> str | None:
        with self._lock:
            page = self._pages.get(url)
            if page is not None:
                self._pages.move_to_end(url)
            return page

    def put_page(self, url: str, html: str) -> None:
        with self._lock:
            self._pages[url] = html
            self._pages.move_to_end(url)
            while len(self._pages) > self.max_pages:
                self._pages.popitem(last=False)

    def drop_page(self, url: str) -> None:
        with self._lock:
            self._pages.pop(url, None)

    def site(self, host: str) -> Site:
        with self._lock:
            return self._sites.setdefault(host, Site())

    def add_note(self, host: str, note: str) -> None:
        site = self.site(host)
        with self._lock:
            if note not in site.notes:
                site.notes.append(note)
                del site.notes[:-5]

    def set_identity(self, host: str, identity: dict) -> None:
        """First page on a site wins: later pages inherit its look."""
        site = self.site(host)
        with self._lock:
            if not site.identity:
                site.identity = identity

    def record_visit(self, host: str, path: str, title: str, stylesheet: str) -> None:
        site = self.site(host)
        with self._lock:
            site.pages[path] = title or path
            site.pages.move_to_end(path)
            while len(site.pages) > self.pages_per_site:
                site.pages.popitem(last=False)
            if stylesheet and not site.stylesheet:
                site.stylesheet = stylesheet
