"""Public model imports.

Models live in ``blog.entities`` by topic.  Keeping these re-exports means old
imports and migration references can continue to use ``blog.models``.
"""

from .entities.accounts import PendingRegistration, UserProfile, avatar_path
from .entities.articles import (
    ArticleModel,
    ArticleQuerySet,
    ArticleSearchDocument,
    Category,
    Tag,
)
from .entities.collections import (
    AudioTrack,
    Bookmark,
    BookmarkCategory,
    Essay,
    FriendCategory,
    FriendLink,
    MasonryImage,
)
from .entities.comments import (
    Comment,
    CommentBadge,
    CommentBadgeAssignment,
    CommentBadgeTranslation,
    CommentEmoji,
    CommentEmojiPack,
    CommentGifSource,
    CommentImage,
    CommentLike,
    CommentNotification,
    TrafficModel,
)
from .entities.navigation import Font, MenuLink, MenuLinkTranslation
from .entities.media import EditorImage, EditorImageLease, EditorImageRef
from .entities.pages import StandalonePage, StandalonePageTranslation
from .entities.reactions import ArticleReactionVote
from .entities.site import SiteConfiguration


# Historical migrations imported this name from ``blog.models``.
user_avatar_upload_to = avatar_path
