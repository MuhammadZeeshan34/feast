from typing import Callable, Dict, Iterable, Optional, Tuple

import pyarrow.parquet as pq
from pyarrow._fs import FileSystem
from pyarrow._s3fs import S3FileSystem
from pyarrow.parquet import ParquetFile
from s3fs import S3FileSystem

from feast import type_map
from feast.data_format import FileFormat, ParquetFormat
from feast.data_source import DataSource
from feast.protos.feast.core.DataSource_pb2 import DataSource as DataSourceProto
from feast.protos.feast.core.SavedDataset_pb2 import (
    SavedDatasetStorage as SavedDatasetStorageProto,
)
from feast.repo_config import RepoConfig
from feast.saved_dataset import SavedDatasetStorage
from feast.value_type import ValueType


class FileSource(DataSource):
    def __init__(
        self,
        path: str,
        name: Optional[str] = "",
        event_timestamp_column: Optional[str] = "",
        file_format: Optional[FileFormat] = None,
        created_timestamp_column: Optional[str] = "",
        field_mapping: Optional[Dict[str, str]] = None,
        date_partition_column: Optional[str] = "",
        s3_endpoint_override: Optional[str] = None,
    ):
        """Create a FileSource from a file containing feature data. Only Parquet format supported.

        Args:

            name (optional): Name for the file source. Defaults to the path.
            path: File path to file containing feature data. Must contain an event_timestamp column, entity columns and
                feature columns.
            event_timestamp_column: Event timestamp column used for point in time joins of feature values.
            created_timestamp_column (optional): Timestamp column when row was created, used for deduplicating rows.
            file_format (optional): Explicitly set the file format. Allows Feast to bypass inferring the file format.
            field_mapping: A dictionary mapping of column names in this data source to feature names in a feature table
                or view. Only used for feature columns, not entities or timestamp columns.
            date_partition_column (optional): Timestamp column used for partitioning.
            s3_endpoint_override (optional): Overrides AWS S3 enpoint with custom S3 storage

        Examples:
            >>> from feast import FileSource
            >>> file_source = FileSource(path="my_features.parquet", event_timestamp_column="event_timestamp")
        """
        if path is None:
            raise ValueError(
                'No "path" argument provided. Please set "path" to the location of your file source.'
            )
        self.file_options = FileOptions(
            file_format=file_format,
            file_url=path,
            s3_endpoint_override=s3_endpoint_override,
        )

        super().__init__(
            name if name else path,
            event_timestamp_column,
            created_timestamp_column,
            field_mapping,
            date_partition_column,
        )

    # Note: Python requires redefining hash in child classes that override __eq__
    def __hash__(self):
        return super().__hash__()

    def __eq__(self, other):
        if not isinstance(other, FileSource):
            raise TypeError("Comparisons should only involve FileSource class objects.")

        return (
            self.name == other.name
            and self.file_options.file_url == other.file_options.file_url
            and self.file_options.file_format == other.file_options.file_format
            and self.event_timestamp_column == other.event_timestamp_column
            and self.created_timestamp_column == other.created_timestamp_column
            and self.field_mapping == other.field_mapping
            and self.file_options.s3_endpoint_override
            == other.file_options.s3_endpoint_override
        )

    @property
    def path(self):
        """
        Returns the path of this file data source.
        """
        return self.file_options.file_url

    @staticmethod
    def from_proto(data_source: DataSourceProto):
        return FileSource(
            name=data_source.name,
            field_mapping=dict(data_source.field_mapping),
            file_format=FileFormat.from_proto(data_source.file_options.file_format),
            path=data_source.file_options.file_url,
            event_timestamp_column=data_source.event_timestamp_column,
            created_timestamp_column=data_source.created_timestamp_column,
            date_partition_column=data_source.date_partition_column,
            s3_endpoint_override=data_source.file_options.s3_endpoint_override,
        )

    def to_proto(self) -> DataSourceProto:
        data_source_proto = DataSourceProto(
            name=self.name,
            type=DataSourceProto.BATCH_FILE,
            field_mapping=self.field_mapping,
            file_options=self.file_options.to_proto(),
        )

        data_source_proto.event_timestamp_column = self.event_timestamp_column
        data_source_proto.created_timestamp_column = self.created_timestamp_column
        data_source_proto.date_partition_column = self.date_partition_column

        return data_source_proto

    def validate(self, config: RepoConfig):
        # TODO: validate a FileSource
        pass

    @staticmethod
    def source_datatype_to_feast_value_type() -> Callable[[str], ValueType]:
        return type_map.pa_to_feast_value_type

    def get_table_column_names_and_types(
        self, config: RepoConfig
    ) -> Iterable[Tuple[str, str]]:
        filesystem, path = FileSource.create_filesystem_and_path(
            self.path, self.file_options.s3_endpoint_override
        )
        if filesystem:
            pq.read_table(path, filesystem=filesystem).to_pandas().to_parquet(
                f"/tmp/{path.split('/')[-1]}"
            )
            path = f"/tmp/{path.split('/')[-1]}"
        schema = ParquetFile(path).schema_arrow
        return zip(schema.names, map(str, schema.types))

    @staticmethod
    def create_filesystem_and_path(
        path: str, s3_endpoint_override: str,
    ) -> Tuple[Optional[FileSystem], str]:
        if path.startswith("s3://"):
            s3fs = S3FileSystem(
                client_kwargs=dict(endpoint_url=s3_endpoint_override)
                if s3_endpoint_override
                else None
            )
            return s3fs, path.replace("s3://", "")
        else:
            return None, path

    def get_table_query_string(self) -> str:
        pass


class FileOptions:
    """
    DataSource File options used to source features from a file
    """

    def __init__(
        self,
        file_format: Optional[FileFormat],
        file_url: Optional[str],
        s3_endpoint_override: Optional[str],
    ):
        """
        FileOptions initialization method

        Args:
            file_format (FileFormat, optional): file source format eg. parquet
            file_url (str, optional): file source url eg. s3:// or local file
            s3_endpoint_override (str, optional): custom s3 endpoint (used only with s3 file_url)
        """
        self._file_format = file_format
        self._file_url = file_url
        self._s3_endpoint_override = s3_endpoint_override

    @property
    def file_format(self):
        """
        Returns the file format of this file
        """
        return self._file_format

    @file_format.setter
    def file_format(self, file_format):
        """
        Sets the file format of this file
        """
        self._file_format = file_format

    @property
    def file_url(self):
        """
        Returns the file url of this file
        """
        return self._file_url

    @file_url.setter
    def file_url(self, file_url):
        """
        Sets the file url of this file
        """
        self._file_url = file_url

    @property
    def s3_endpoint_override(self):
        """
        Returns the s3 endpoint override
        """
        return None if self._s3_endpoint_override == "" else self._s3_endpoint_override

    @s3_endpoint_override.setter
    def s3_endpoint_override(self, s3_endpoint_override):
        """
        Sets the s3 endpoint override
        """
        self._s3_endpoint_override = s3_endpoint_override

    @classmethod
    def from_proto(cls, file_options_proto: DataSourceProto.FileOptions):
        """
        Creates a FileOptions from a protobuf representation of a file option

        args:
            file_options_proto: a protobuf representation of a datasource

        Returns:
            Returns a FileOptions object based on the file_options protobuf
        """
        file_options = cls(
            file_format=FileFormat.from_proto(file_options_proto.file_format),
            file_url=file_options_proto.file_url,
            s3_endpoint_override=file_options_proto.s3_endpoint_override,
        )
        return file_options

    def to_proto(self) -> DataSourceProto.FileOptions:
        """
        Converts an FileOptionsProto object to its protobuf representation.

        Returns:
            FileOptionsProto protobuf
        """

        file_options_proto = DataSourceProto.FileOptions(
            file_format=(
                None if self.file_format is None else self.file_format.to_proto()
            ),
            file_url=self.file_url,
            s3_endpoint_override=self.s3_endpoint_override,
        )

        return file_options_proto


class SavedDatasetFileStorage(SavedDatasetStorage):
    _proto_attr_name = "file_storage"

    file_options: FileOptions

    def __init__(
        self,
        path: str,
        file_format: FileFormat = ParquetFormat(),
        s3_endpoint_override: Optional[str] = None,
    ):
        self.file_options = FileOptions(
            file_url=path,
            file_format=file_format,
            s3_endpoint_override=s3_endpoint_override,
        )

    @staticmethod
    def from_proto(storage_proto: SavedDatasetStorageProto) -> SavedDatasetStorage:
        file_options = FileOptions.from_proto(storage_proto.file_storage)
        return SavedDatasetFileStorage(
            path=file_options.file_url,
            file_format=file_options.file_format,
            s3_endpoint_override=file_options.s3_endpoint_override,
        )

    def to_proto(self) -> SavedDatasetStorageProto:
        return SavedDatasetStorageProto(file_storage=self.file_options.to_proto())

    def to_data_source(self) -> DataSource:
        return FileSource(
            path=self.file_options.file_url,
            file_format=self.file_options.file_format,
            s3_endpoint_override=self.file_options.s3_endpoint_override,
        )
