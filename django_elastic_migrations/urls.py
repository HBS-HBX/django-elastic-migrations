# -*- coding: utf-8 -*-
"""
URLs for django_elastic_migrations.
"""

from django.urls import re_path
from django.views.generic import TemplateView

urlpatterns = [
    re_path(r'', TemplateView.as_view(template_name="django_elastic_migrations/base.html")),
]
