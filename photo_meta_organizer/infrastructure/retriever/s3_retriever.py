"""Amazon S3 implementation of image file retrieval.

This module provides a concrete implementation of the ImageRetriever protocol
for discovering and accessing image files stored in Amazon S3 buckets.
Supports pagination to handle large buckets efficiently.
"""

from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Generator

import boto3

from photo_meta_organizer.application.interfaces.image_retriever import (
    ImageRetriever,
    RemoteFileHandle,
)


class S3ImageRetriever:
    """Retrieves image files from Amazon S3 buckets.

    This class implements the ImageMetadataRetriever protocol to discover and
    stream image files from an S3 bucket. It handles pagination automatically
    to support large buckets with thousands of objects.

    The implementation uses boto3 for AWS API access and streams file contents
    directly from S3 without downloading entire objects into memory.

    Attributes:
        bucket_name: The S3 bucket name.
        prefix: Optional prefix to filter objects (e.g., "photos/").

    Example:
        >>> retriever = S3ImageRetriever("my-bucket", prefix="images/")
        >>> for file_handle in retriever.list_files():
        ...     with retriever.get_file_stream(file_handle) as stream:
        ...         data = stream.read()
    """

    def __init__(self, bucket_name: str, prefix: str = "") -> None:
        """Initialize the S3 retriever.

        Args:
            bucket_name: The S3 bucket to retrieve files from.
            prefix: Optional prefix to filter objects (default: empty string).

        Raises:
            ValueError: If bucket_name is empty.
        """
        if not bucket_name:
            raise ValueError("bucket_name cannot be empty")
        self._s3_client: Any = boto3.client("s3")
        self._bucket_name = bucket_name
        self._prefix = prefix

    def list_files(self) -> Generator[RemoteFileHandle, None, None]:
        """Discover all objects in the S3 bucket with the given prefix.

        Uses pagination to handle buckets with more than 1000 objects.
        Automatically filters out directory markers (keys ending with '/').

        Yields:
            RemoteFileHandle: Metadata for each discovered object.
        """
        paginator = self._s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket_name, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Skip directory markers
                if key.endswith("/"):
                    continue

                yield RemoteFileHandle(
                    original_path=key,
                    filename=PurePosixPath(key).name,
                    size_bytes=obj["Size"],
                )

    @contextmanager
    def get_file_stream(
        self, file_handle: RemoteFileHandle
    ) -> Generator[BinaryIO, None, None]:
        """Retrieve a binary stream for a specific S3 object.

        Args:
            file_handle: The file handle returned by list_files().

        Yields:
            A binary stream from which the S3 object contents can be read.

        Raises:
            ClientError: If the object cannot be retrieved from S3.

        Example:
            >>> with retriever.get_file_stream(handle) as stream:
            ...     content = stream.read()
        """
        response = self._s3_client.get_object(
            Bucket=self._bucket_name, Key=file_handle.original_path
        )
        body = response["Body"]
        try:
            yield body
        finally:
            body.close()
