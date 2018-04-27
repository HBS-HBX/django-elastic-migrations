# -*- coding: utf-8 -*-
"""
Database models for django_elastic_migrations.
"""

from __future__ import absolute_import, unicode_literals

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from model_utils import Choices
from model_utils.models import TimeFramedModel, SoftDeletableModel, StatusModel


@python_2_unicode_compatible
class IndexMaster(models.Model):
    """
    Model that retains information about all Indexes
    """
    name = models.CharField(verbose_name="Index Name", max_length=32, unique=True)
    active_index_instance = models.ForeignKey('IndexInstance')

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<IndexMaster, ID: {}>'.format(self.id)


@python_2_unicode_compatible
class IndexInstance(SoftDeletableModel, TimeFramedModel):
    """
    Each Schema model represents index settings at a particular
    point in time.
    """
    schema = models.TextField(verbose_name="Elasticsearch Schema JSON")
    version = models.CharField(verbose_name="Codebase Version", max_length=64)
    index_master = models.ForeignKey(IndexMaster)

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<IndexInstance, ID: {}>'.format(self.id)

    @property
    def is_active(self):
        return self.id == self.index_master.active_index_instance

@python_2_unicode_compatible
class IndexAction(TimeFramedModel, StatusModel):
    """
    Each Action is a change to an Elasticsearch index.
    """
    STATUS = Choices('queued', 'started', 'in progress', 'complete')
    log = models.TextField
    index_master = models.ForeignKey(IndexMaster)
    index_instance = models.ForeignKey(IndexInstance)

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return '<IndexAction, ID: {}>'.format(self.id)
