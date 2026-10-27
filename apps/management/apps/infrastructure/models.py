"""Administrative resource organization; membership never grants resource access."""

from django.db import models


class Cluster(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClusterNode(models.Model):
    cluster = models.ForeignKey(Cluster, on_delete=models.PROTECT, related_name='members')
    node = models.OneToOneField('nodes.Node', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.cluster_id}:{self.node_id}'


class ResourcePool(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default='')
    cluster = models.ForeignKey(Cluster, on_delete=models.PROTECT, related_name='pools')
    vcpu_limit = models.PositiveIntegerField(default=32)
    memory_mib_limit = models.PositiveIntegerField(default=65536)
    disk_gib_limit = models.PositiveIntegerField(default=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PoolInstance(models.Model):
    pool = models.ForeignKey(ResourcePool, on_delete=models.PROTECT, related_name='members')
    instance = models.OneToOneField('instances.Instance', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.pool_id}:{self.instance_id}'


class ConsoleConfiguration(models.Model):
    # A fixed primary key implements a single versioned configuration record.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    revision = models.PositiveIntegerField(default=1)
    values = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Console configuration v{self.revision}'
