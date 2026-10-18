# Administration guide

The Django administration site manages blog content, comments, and Redefine
settings. It's built on Django's stock admin, so staff accounts use normal
Django permissions rather than a separate blog permission model.

## Dashboard

The dashboard shows published articles, drafts, pending comments, today's
traffic, and the active site configuration. Quick links open the most common
authoring and moderation pages.

## Finding settings

Open a site configuration and use the search box above the first section. It
searches section names, field labels, and help text. Press `Ctrl+K` (`Cmd+K` on
macOS) to focus it. On list pages, the same shortcut focuses Django's navigation
or list search.

Every editable `SiteConfiguration` field is represented in the form. Settings
are grouped by identity, appearance, banner, navigation, comments, articles,
code and TOC, extensions, music, SEO/footer, standalone pages, and advanced
injections.

## Configuration safety

- Only one site configuration can be active at a time.
- The last configuration and the active configuration cannot be deleted.
- Provider credentials are validated before saving, and switching comment
  providers does not delete saved options for other providers.
- JSON fields enforce their expected array or object shape.
- RSS can use the native `/feed.xml` endpoint without extra configuration, or
  link to an external provider when an RSS URL is supplied.
- Missing analytics or ICP values and out-of-range theme values are reported on
  the relevant field.

## Content and moderation tools

- Article lists support search, filters, date navigation, and bulk publishing,
  comment toggling, and withdrawal.
- Comments support content, user, and article search plus bulk approval and
  pinning. Only one comment per article can be pinned; duplicate bulk choices
  are reduced to the newest selected comment.
- Frontend deletion and pinning follow the `delete_comment` and
  `change_comment` permissions instead of granting every staff account the same
  moderation power. Comment authors can still delete their own comments.
- Notifications can be marked read or unread in bulk.
- Menus, fonts, emojis, GIF sources, bookmarks, essays, masonry entries, and
  friend links have dedicated searchable pages.
- Traffic records are searchable and read-only.
