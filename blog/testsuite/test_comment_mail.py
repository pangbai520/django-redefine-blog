from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase

from blog.models import ArticleModel, Comment, CommentNotification, SiteConfiguration
from blog.services.mail import notify


User = get_user_model()


class CommentMailTests(TestCase):
    def setUp(self):
        self.site = SiteConfiguration.objects.create(
            config_name="Mail tests",
            site_name="Mail Blog",
            colour_primary="#00bbfe",
            comment_email_notifications=True,
            is_active=True,
        )
        self.recipient = User.objects.create_user(
            "recipient", email="recipient@example.com"
        )
        self.recipient.profile.language_code = "zh-hans"
        self.recipient.profile.save(update_fields=("language_code",))
        self.actor = User.objects.create_user("actor")
        self.actor.profile.display_name = "Reply Reader"
        self.actor.profile.save(update_fields=("display_name",))
        self.article = ArticleModel.objects.create(
            title="Mail article",
            slug="mail-article",
            content="Content",
            is_published=True,
        )

    def test_localized_html(self):
        comment = Comment.objects.create(
            article=self.article,
            author=self.actor,
            content="A helpful reply",
        )
        request = RequestFactory().get("/")

        notify(
            request,
            self.recipient,
            self.actor,
            comment,
            CommentNotification.REPLY,
        )

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("回复了您的评论", message.subject)
        self.assertIn("A helpful reply", message.body)
        self.assertIn(f"#comment-{comment.pk}", message.body)
        self.assertEqual(len(message.alternatives), 1)
        html = message.alternatives[0].content
        self.assertIn("查看评论", html)
        self.assertIn("#00bbfe", html)
        self.assertIn("mail-card", html)

    def test_event_dedup(self):
        comment = Comment.objects.create(
            article=self.article,
            author=self.recipient,
            content="Original comment",
        )
        request = RequestFactory().get("/")

        for _attempt in range(2):
            notify(
                request,
                self.recipient,
                self.actor,
                comment,
                CommentNotification.LIKE,
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(CommentNotification.objects.count(), 1)
