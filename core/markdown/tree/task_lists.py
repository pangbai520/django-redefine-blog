import re
import xml.etree.ElementTree as etree

from markdown.treeprocessors import Treeprocessor


class TaskListProcessor(Treeprocessor):
    """Convert GFM task markers into accessible, disabled checkboxes."""

    MARKER_RE = re.compile(r"^\[([ xX])\]\s+")

    def run(self, root):
        for task_list in root.iter():
            if task_list.tag not in {"ul", "ol"}:
                continue
            has_tasks = False
            for item in task_list.findall("li"):
                text_holder = item
                if len(item) and item[0].tag == "p":
                    text_holder = item[0]
                marker = self.MARKER_RE.match(text_holder.text or "")
                if not marker:
                    continue

                has_tasks = True
                item_text = (text_holder.text or "")[marker.end():]
                text_holder.text = None
                checkbox = etree.Element("input", {
                    "class": "task-list-item-checkbox",
                    "type": "checkbox",
                    "disabled": "disabled",
                })
                if marker.group(1).lower() == "x":
                    checkbox.set("checked", "checked")
                checkbox.tail = f" {item_text}"
                text_holder.insert(0, checkbox)
                item.set("class", self._append_class(item.get("class"), "task-list-item"))

            if has_tasks:
                task_list.set(
                    "class",
                    self._append_class(task_list.get("class"), "contains-task-list"),
                )
        return root

    @staticmethod
    def _append_class(existing, value):
        classes = (existing or "").split()
        if value not in classes:
            classes.append(value)
        return " ".join(classes)
