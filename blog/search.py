import re

from django.core.cache import cache
from django.db import DatabaseError, connection, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils.html import strip_tags
from django.utils import timezone
from markdown import Markdown

from .cache_utils import query_cache_key
from .models import ArticleModel, ArticleSearchDocument


SQLITE_FTS_TABLE = "blog_article_search_fts"
MYSQL_INDEX_NAME = "blog_article_search_fulltext"
POSTGRES_INDEX_NAME = "blog_article_search_vector"
SEARCH_LIMIT = 20


def _plain_text(value):
    try:
        return strip_tags(Markdown(extensions=("nl2br", "tables")).convert(value or ""))
    except Exception:
        return re.sub(r"\s+", " ", value or "")


def index_article(article):
    document, _ = ArticleSearchDocument.objects.update_or_create(
        article=article,
        defaults={
            "title": article.title,
            "excerpt": article.excerpt,
            "content": _plain_text(article.content),
        },
    )
    if connection.vendor == "sqlite" and _sqlite_fts_exists():
        _sync_sqlite_document(document)
    return document


def remove_article_from_index(article_id):
    ArticleSearchDocument.objects.filter(article_id=article_id).delete()
    if connection.vendor == "sqlite" and _sqlite_fts_exists():
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {SQLITE_FTS_TABLE} WHERE rowid = %s", [article_id])


def rebuild_search_index():
    with transaction.atomic():
        ArticleSearchDocument.objects.exclude(
            article_id__in=ArticleModel.objects.values("pk")
        ).delete()
        for article in ArticleModel.objects.all().iterator(chunk_size=200):
            index_article(article)
    vendor_index = rebuild_vendor_index()
    return ArticleSearchDocument.objects.count(), vendor_index


def rebuild_vendor_index():
    if connection.vendor == "sqlite":
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS {SQLITE_FTS_TABLE} "
                    "USING fts5(title, content, tokenize='trigram')"
                )
                cursor.execute(f"DELETE FROM {SQLITE_FTS_TABLE}")
                rows = ArticleSearchDocument.objects.values_list(
                    "article_id", "title", "content"
                )
                cursor.executemany(
                    f"INSERT INTO {SQLITE_FTS_TABLE}(rowid, title, content) VALUES (%s, %s, %s)",
                    rows,
                )
            return "sqlite-fts5"
        except DatabaseError:
            return "database-fallback"
    if connection.vendor == "mysql":
        # MySQL implicitly commits around ALTER TABLE. Running this DDL from a
        # Django TestCase or another caller-owned transaction would corrupt the
        # surrounding transaction and leak data across tests. The portable
        # search backend remains correct until the index can be built outside
        # that transaction.
        if connection.in_atomic_block:
            return "database-fallback"
        try:
            table = ArticleSearchDocument._meta.db_table
            with connection.cursor() as cursor:
                cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", [MYSQL_INDEX_NAME])
                if cursor.fetchone() is None:
                    cursor.execute(
                        f"ALTER TABLE `{table}` ADD FULLTEXT INDEX `{MYSQL_INDEX_NAME}` "
                        "(`title`, `content`) WITH PARSER ngram"
                    )
            return "mysql-fulltext"
        except DatabaseError:
            return "database-fallback"
    if connection.vendor == "postgresql":
        try:
            # A savepoint is required when this command is called from a
            # surrounding transaction (for example Django TestCase). A
            # recoverable DDL error must not leave that transaction aborted.
            with transaction.atomic():
                table = ArticleSearchDocument._meta.db_table
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'CREATE INDEX IF NOT EXISTS "{POSTGRES_INDEX_NAME}" '
                        f'ON "{table}" USING GIN '
                        "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')))"
                    )
            return "postgresql-search-vector"
        except DatabaseError:
            return "database-fallback"
    return "database-fallback"


def _sqlite_fts_exists():
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = %s",
                [SQLITE_FTS_TABLE],
            )
            return cursor.fetchone() is not None
    except DatabaseError:
        return False


def _sync_sqlite_document(document):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {SQLITE_FTS_TABLE} WHERE rowid = %s",
                [document.article_id],
            )
            cursor.execute(
                f"INSERT INTO {SQLITE_FTS_TABLE}(rowid, title, content) VALUES (%s, %s, %s)",
                [document.article_id, document.title, document.content],
            )
    except DatabaseError:
        pass


def _tokens(query):
    return [token for token in re.findall(r"[\w\u4e00-\u9fff]+", query.lower()) if token]


def _database_results(query, limit):
    documents = ArticleSearchDocument.objects.select_related("article").filter(
        article__is_published=True,
        article__created_at__lte=timezone.now(),
    )
    for token in _tokens(query):
        documents = documents.filter(
            Q(title__icontains=token)
            | Q(excerpt__icontains=token)
            | Q(content__icontains=token)
        )
    return list(
        documents.annotate(
            search_rank=Case(
                When(title__iexact=query, then=Value(300)),
                When(title__icontains=query, then=Value(200)),
                When(excerpt__icontains=query, then=Value(100)),
                default=Value(10),
                output_field=IntegerField(),
            )
        ).order_by("-search_rank", "-article__created_at")[:limit]
    )


def _sqlite_results(query, limit):
    compact = "".join(_tokens(query))
    if len(compact) < 3 or not _sqlite_fts_exists():
        return None
    match_query = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in _tokens(query))
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT rowid FROM {SQLITE_FTS_TABLE} WHERE {SQLITE_FTS_TABLE} MATCH %s "
                "ORDER BY bm25(blog_article_search_fts, 8.0, 1.0) LIMIT %s",
                [match_query, limit],
            )
            ids = [row[0] for row in cursor.fetchall()]
    except DatabaseError:
        return None
    return _documents_in_order(ids)


def _mysql_results(query, limit):
    table = ArticleSearchDocument._meta.db_table
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT article_id FROM `{table}` WHERE MATCH(title, content) "
                "AGAINST (%s IN NATURAL LANGUAGE MODE) ORDER BY "
                "MATCH(title, content) AGAINST (%s IN NATURAL LANGUAGE MODE) DESC LIMIT %s",
                [query, query, limit],
            )
            ids = [row[0] for row in cursor.fetchall()]
    except DatabaseError:
        return None
    return _documents_in_order(ids)


def _postgresql_results(query, limit):
    # PostgreSQL's built-in dictionaries do not segment continuous CJK text.
    # Keep those queries correct with the portable substring backend unless a
    # deployment later opts into a dedicated tokenizer.
    if re.search(r"[\u3400-\u9fff]", query):
        return None
    try:
        table = ArticleSearchDocument._meta.db_table
        vector = "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))"
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT article_id FROM "{table}" '
                f"WHERE {vector} @@ websearch_to_tsquery('simple', %s) "
                f"ORDER BY ts_rank({vector}, websearch_to_tsquery('simple', %s)) DESC "
                "LIMIT %s",
                [query, query, limit],
            )
            ids = [row[0] for row in cursor.fetchall()]
        return _documents_in_order(ids)
    except DatabaseError:
        return None


def _documents_in_order(ids):
    if not ids:
        return []
    ordering = Case(
        *(When(article_id=article_id, then=position) for position, article_id in enumerate(ids)),
        output_field=IntegerField(),
    )
    return list(
        ArticleSearchDocument.objects.select_related("article")
        .filter(article_id__in=ids, article__in=ArticleModel.objects.published())
        .order_by(ordering)
    )


def _snippet(document, query, length=220):
    text = document.excerpt or document.content
    folded = text.casefold()
    positions = [folded.find(token.casefold()) for token in _tokens(query)]
    positions = [position for position in positions if position >= 0]
    start = max(0, (min(positions) if positions else 0) - 50)
    end = min(len(text), start + length)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def search_articles(query, limit=SEARCH_LIMIT):
    query = re.sub(r"\s+", " ", (query or "").strip())[:100]
    if not query or not _tokens(query):
        return [], "empty"
    limit = max(1, min(int(limit), 50))
    key = query_cache_key("search", f"{connection.vendor}:{limit}:{query.casefold()}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    backend = "database-fallback"
    documents = None
    if connection.vendor == "sqlite":
        documents = _sqlite_results(query, limit)
        if documents is not None:
            backend = "sqlite-fts5"
    elif connection.vendor == "mysql":
        documents = _mysql_results(query, limit)
        if documents is not None:
            backend = "mysql-fulltext"
    elif connection.vendor == "postgresql":
        documents = _postgresql_results(query, limit)
        if documents is not None:
            backend = "postgresql-search-vector"
    if documents is None:
        documents = _database_results(query, limit)

    results = [
        {
            "title": document.title,
            "content": _snippet(document, query),
            "url": document.article.get_absolute_url(),
        }
        for document in documents
    ]
    payload = (results, backend)
    cache.set(key, payload, 15 * 60)
    return payload
