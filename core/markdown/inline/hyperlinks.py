import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from markdown.treeprocessors import Treeprocessor

class LinkIconProcessor(Treeprocessor):
    def __init__(self, md, add_icon=True, internal_hosts=None):
        super().__init__(md)
        self.add_icon = add_icon
        self.internal_hosts = {
            host.lower().lstrip(".")
            for host in (internal_hosts or ())
            if host and host != "*"
        }

    def _is_internal(self, hostname):
        hostname = (hostname or "").lower().rstrip(".")
        return any(
            hostname == host or hostname.endswith(f".{host}")
            for host in self.internal_hosts
        )

    def run(self, root):
        for a in root.iter('a'):
            href = a.get('href', '')

            # limit the affordance to absolute external text links, so relative
            # navigation and linked images retain their original behavior
            parsed = urlparse(href)
            if (
                parsed.scheme not in ('http', 'https')
                or self._is_internal(parsed.hostname)
                or len(a) > 0
            ):
                continue

            existing_class = a.get('class', '')
            a.set('class', f"{existing_class} link".strip())
            a.set('target', '_blank')
            a.set('rel', 'noopener')

            if self.add_icon:
                icon = ET.Element('i', {
                    'class': 'fa-solid fa-arrow-up-right ml-[0.2em] font-light align-text-top text-[0.7em] link-icon'
                })
                a.append(icon)

        return root
