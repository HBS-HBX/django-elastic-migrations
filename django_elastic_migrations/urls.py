# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function, unicode_literals)
"""
URLs for django_elastic_migrations.
"""

from django.conf.urls import url
from django.views.generic import TemplateView

urlpatterns = [
    url(r'', TemplateView.as_view(template_name="django_elastic_migrations/base.html")),
]
