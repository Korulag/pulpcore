import gc

from django.conf import settings
from django.utils import timezone

from pulpcore.app.models import (
    Artifact,
    Content,
    ProgressReport,
    PublishedMetadata,
    PulpTemporaryFile,
    Upload,
)


def queryset_iterator(qs, batchsize=2000, gc_collect=True):
    """
    Provide a batching functionality that returns individual querysets per batch.

    Copied from here with minor changes:
    https://www.guguweb.com/2020/03/27/optimize-django-memory-usage/
    """
    iterator = qs.values_list("pk", flat=True).order_by("pk").distinct().iterator()
    eof = False
    while not eof:
        primary_key_buffer = []
        try:
            while len(primary_key_buffer) < batchsize:
                primary_key_buffer.append(next(iterator))
        except StopIteration:
            eof = True
        yield qs.filter(pk__in=primary_key_buffer).order_by("pk")
        if gc_collect:
            gc.collect()


def orphan_cleanup(content_pks=None, orphan_protection_time=settings.ORPHAN_PROTECTION_TIME):
    """
    Delete all orphan Content and Artifact records.
    Go through orphan Content multiple times to remove content from subrepos.
    This task removes Artifact files from the filesystem as well.

    Kwargs:
        content_pks (list): A list of content pks. If specified, only remove these orphans.

    """
    with ProgressReport(
        message="Clean up orphan Content",
        total=None,
        code="clean-up.content",
    ) as progress_bar:
        while True:
            content = Content.objects.orphaned(orphan_protection_time, content_pks).exclude(
                pulp_type=PublishedMetadata.get_pulp_type()
            )
            content_count = content.count()
            if not content_count:
                break

            # delete the content
            for c in queryset_iterator(content):
                progress_bar.increase_by(c.count())
                c.delete()

    # delete the artifacts that don't belong to any content
    artifacts = Artifact.objects.orphaned(orphan_protection_time)

    with ProgressReport(
        message="Clean up orphan Artifacts",
        total=artifacts.count(),
        code="clean-up.artifacts",
    ) as progress_bar:
        for artifact in progress_bar.iter(artifacts.iterator()):
            # we need to manually call delete() because it cleans up the file on the filesystem
            artifact.delete()


def upload_cleanup():
    assert settings.UPLOAD_PROTECTION_TIME > 0
    expiration = timezone.now() - timezone.timedelta(minutes=settings.UPLOAD_PROTECTION_TIME)
    qs = Upload.objects.filter(pulp_created__lt=expiration)
    with ProgressReport(
        message="Clean up uploads",
        total=qs.count(),
        code="clean-up.uploads",
    ) as pr:
        for upload in pr.iter(qs):
            upload.delete()


def tmpfile_cleanup():
    assert settings.TMPFILE_PROTECTION_TIME > 0
    expiration = timezone.now() - timezone.timedelta(minutes=settings.TMPFILE_PROTECTION_TIME)
    qs = PulpTemporaryFile.objects.filter(pulp_created__lt=expiration)
    with ProgressReport(
        message="Clean up shared temporary files",
        total=qs.count(),
        code="clean-up.tmpfiles",
    ) as pr:
        for tmpfile in pr.iter(qs):
            tmpfile.delete()
