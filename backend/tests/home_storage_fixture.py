"""Immutable generation-aware storage double. No cloud credentials or requests."""
from google.api_core.exceptions import PreconditionFailed, NotFound


class Bucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name, generation=None):
        return Blob(self, name, generation)


class Blob:
    def __init__(self, bucket, name, generation):
        self.bucket, self.name, self.generation = bucket, name, generation
        self.size, self.content_type = None, None

    def upload_from_string(self, value, *, content_type, if_generation_match, timeout):
        assert if_generation_match == 0
        if self.name in self.bucket.objects:
            raise PreconditionFailed('already exists')
        self.bucket.objects[self.name] = (value, content_type, 1)
        self.reload(timeout=timeout)

    def reload(self, *, timeout):
        value = self.bucket.objects.get(self.name)
        if value is None or self.generation is not None and int(self.generation) != value[2]:
            raise NotFound('missing generation')
        self.size, self.content_type, self.generation = len(value[0]), value[1], value[2]

    def download_as_bytes(self, *, timeout):
        self.reload(timeout=timeout)
        return self.bucket.objects[self.name][0]
