# Django Admin

Most of the blog can be maintained without touching Python or template files.
After creating a superuser, open `/admin/`.

## First setup

Start with **Site configurations**. The active configuration controls the site
name, colours, home banner, sidebar, comments, footer and the optional pages.
There must always be one configuration, and only one can be active.

The other pages are ordinary content tables:

- **Articles**, **Categories** and **Tags** contain the blog itself.
- **Menu links** build the navigation bar and sidebar menus.
- **Friend links**, **Bookmarks**, **Essays** and **Masonry images** feed their
  matching public pages.
- **Audio tracks**, **Fonts** and the comment asset tables are optional.

The site-configuration form is long by necessity. Its search box filters the
sections by field name and help text; `Ctrl+K` (`Cmd+K` on macOS) focuses it.

## Publishing

An article can be saved as a draft or published immediately. A published
article whose date is in the future stays hidden until that time. Changing a
slug changes its public URL, so avoid doing that after sharing the post.

The article list has bulk actions for publishing, withdrawing and changing the
comment switch. Search and date navigation are usually quicker than editing
posts one by one.

## Comments

Pending comments can be approved from the list page. Only one comment can be
pinned on each article. Comment deletion and pinning use Django's normal model
permissions, so a staff account does not automatically receive every moderation
action.

The **Blogger** badge is created with the starter configuration and is assigned
to superusers automatically. Badge colours may either follow the active theme
or use an explicit colour.

Traffic records are read-only in the admin. They are useful for a quick check,
not a replacement for a full analytics service.
