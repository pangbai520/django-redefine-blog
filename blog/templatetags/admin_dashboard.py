from django import template
from django.utils import timezone

from blog.models import ArticleModel, Comment, SiteConfiguration, TrafficModel


register = template.Library()


@register.simple_tag
def admin_dashboard_stats():
    """Return small, actionable counts for the custom admin dashboard."""
    today = timezone.localdate()
    active = SiteConfiguration.objects.filter(is_active=True).first()
    return {
        "published_articles": ArticleModel.objects.published().count(),
        "draft_articles": ArticleModel.objects.filter(is_published=False).count(),
        "pending_comments": Comment.objects.filter(is_approved=False).count(),
        "visits_today": TrafficModel.objects.filter(created_at__date=today).count(),
        "active_config": active.config_name if active else "未设置",
    }
