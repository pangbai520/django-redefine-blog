from django.contrib.staticfiles.apps import StaticFilesConfig


class BlogStaticFilesConfig(StaticFilesConfig):
    """Keep third-party demo pages out of the production static tree."""

    ignore_patterns = [
        *StaticFilesConfig.ignore_patterns,
        "mdeditor/js/lib/codemirror/mode/*.html",
        "mdeditor/js/lib/codemirror/mode/*/*.html",
        r"mdeditor\js\lib\codemirror\mode\*.html",
        r"mdeditor\js\lib\codemirror\mode\*\*.html",
    ]
