from django.urls import path
from .views_redirect import post_login_redirect

urlpatterns = [
    path('redir/', post_login_redirect, name='post_login_redirect'),
]
