"""Django admin module loader.

Admin classes are grouped by feature under ``blog.admin_parts``.  The aliases
below keep the small public API used by older tests and integrations.
"""

from . import models as blog_models
from .admin_labels import apply_admin_metadata

apply_admin_metadata(vars(blog_models))

from .admin_parts import accounts as _accounts  # noqa: F401
from .admin_parts import comments as _comments  # noqa: F401
from .admin_parts import content as _content  # noqa: F401
from .admin_parts import pages as _pages  # noqa: F401
from .admin_parts import site as _site  # noqa: F401

ArticleAdmin = _content.ArticleAdmin
FriendCategoryAdmin = _content.FriendCategoryAdmin
SiteConfigurationAdmin = _site.SiteConfigurationAdmin
SiteConfigurationForm = _site.SiteConfigurationForm
