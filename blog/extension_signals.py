from django.dispatch import Signal


# The instance argument is always an ArticleModel. ``created`` is included for
# published events so integrations can distinguish first publication from edits.
article_published = Signal()
article_unpublished = Signal()
article_deleted = Signal()
