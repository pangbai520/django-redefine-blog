from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from blog import account_views as views

urlpatterns = [
    path("comments/register/", views.register, name="comment_register"),
    path("comments/login/", views.login_view, name="comment_login"),
    path("comments/logout/", views.logout_view, name="comment_logout"),
    path("comments/profile/", views.profile, name="comment_profile"),
    path(
        "comments/settings/delete-account/",
        views.delete_account,
        name="comment_delete_account",
    ),
    path(
        "comments/account-deleted/",
        views.account_deleted,
        name="comment_account_deleted",
    ),
    path(
        "comments/profile/email/<str:token>/",
        views.profile_email_confirm,
        name="comment_profile_email_confirm",
    ),
    path(
        "comments/verify/<uidb64>/<token>/",
        views.verify,
        name="comment_verify",
    ),
    path(
        "comments/password-reset/",
        views.RateLimitedPasswordResetView.as_view(
            template_name="comments/password_reset_form.html",
            email_template_name="emails/password_reset.txt",
            html_email_template_name="emails/password_reset.html",
            subject_template_name="emails/password_reset_subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "comments/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="comments/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "comments/password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="comments/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "comments/password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="comments/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "comments/password-change/",
        views.profile_password_redirect,
        name="password_change",
    ),
    path(
        "comments/password-change/done/",
        views.profile_password_redirect,
        name="password_change_done",
    ),
]
