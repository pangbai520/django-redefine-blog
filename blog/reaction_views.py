import json
import secrets

from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import ArticleModel, ArticleReactionVote, SiteConfiguration
from .services.throttle import rate_limited

COOKIE_NAME = "article_reaction_id"
COOKIE_SALT = "blog.article-reaction"
COOKIE_AGE = 60 * 60 * 24 * 365
REACTION_COUNT = 6


def _visitor(request):
    token = request.get_signed_cookie(
        COOKIE_NAME,
        default=None,
        salt=COOKIE_SALT,
        max_age=COOKIE_AGE,
    )
    if token:
        return token, False
    return secrets.token_urlsafe(32), True


def _counts(article):
    rows = (
        article.reaction_votes.values("reaction")
        .annotate(total=Count("id"))
        .order_by()
    )
    counts = [0] * REACTION_COUNT
    for row in rows:
        index = row["reaction"]
        if index < REACTION_COUNT:
            counts[index] = row["total"]
    return counts


def _response(payload, request, token, is_new, *, status=200):
    response = JsonResponse(payload, status=status)
    if is_new:
        response.set_signed_cookie(
            COOKIE_NAME,
            token,
            salt=COOKIE_SALT,
            max_age=COOKIE_AGE,
            secure=request.is_secure(),
            httponly=True,
            samesite="Lax",
        )
    return response


@require_http_methods(["GET", "POST"])
def article_reactions(request, slug):
    site = SiteConfiguration.get_config()
    article = get_object_or_404(
        ArticleModel.objects.published(),
        slug=slug,
        show_reaction=True,
    )
    if not site.article_reaction_enabled:
        return JsonResponse({"detail": "Not found."}, status=404)

    token, is_new = _visitor(request)
    visitor = ArticleReactionVote.visitor_hash(token)

    if request.method == "POST":
        if rate_limited(request, "article-reaction", limit=60, period=60):
            return _response(
                {"detail": "Too many requests."},
                request,
                token,
                is_new,
                status=429,
            )
        try:
            payload = json.loads(request.body or b"{}")
            index = payload.get("index")
        except (TypeError, ValueError, json.JSONDecodeError):
            index = None
        if isinstance(index, bool) or not isinstance(index, int):
            return _response(
                {"detail": "Invalid reaction."},
                request,
                token,
                is_new,
                status=400,
            )
        if index < 0 or index >= REACTION_COUNT:
            return _response(
                {"detail": "Invalid reaction."},
                request,
                token,
                is_new,
                status=400,
            )

        with transaction.atomic():
            # Lock the article row as well as an existing vote. The extra lock
            # also serializes the first vote from two simultaneous tabs.
            ArticleModel.objects.select_for_update().get(pk=article.pk)
            vote = (
                ArticleReactionVote.objects.select_for_update()
                .filter(article=article, visitor=visitor)
                .first()
            )
            if vote and vote.reaction == index:
                vote.delete()
                active = None
            elif vote:
                vote.reaction = index
                vote.save(update_fields=("reaction", "updated_at"))
                active = index
            else:
                ArticleReactionVote.objects.create(
                    article=article,
                    visitor=visitor,
                    reaction=index,
                )
                active = index
    else:
        active = (
            ArticleReactionVote.objects.filter(article=article, visitor=visitor)
            .values_list("reaction", flat=True)
            .first()
        )

    return _response(
        {"counts": _counts(article), "active": active},
        request,
        token,
        is_new,
    )
