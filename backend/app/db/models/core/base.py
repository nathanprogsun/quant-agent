"""DB Model base classes."""

import inspect
import types
import typing
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import FieldInfo
from sqlalchemy import Row
from sqlalchemy.orm import DeclarativeBase

from app.common.type.patch_request import (
    AbstractUnsetAwareModel,
    AbstractUnsetAwareT,
    is_unset_type,
    specified,
)
from app.util.pydantic_types.time import ZoneRequiredDateTime
from app.util.time import zoned_utc_now

DBModelT = TypeVar("DBModelT", bound="DBModel")
AnyT = TypeVar("AnyT", bound=Any)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


def from_row(adapter, row: Row[Any]):
    """Convert a row object to an arbitrary object that can be deserialized via pydantic TypeAdapter."""
    return adapter.validate_python(row._asdict())


class DBModel(BaseModel):
    """Base model to interact directly with DB IO."""

    model_config = ConfigDict(frozen=True, use_enum_values=True, validate_default=True)

    @classmethod
    def model_required_fields(cls) -> set[str]:
        return {f_name for f_name, f_info in cls.model_fields.items() if f_info.is_required()}

    @classmethod
    def from_row(
        cls: type[DBModelT],
        r: Row[Any],
        *,
        column_alias_prefix: str | None = None,
        additional_cols: dict[str, Any] | None = None,
    ) -> DBModelT:
        result_dict: dict[str, Any] = {}
        d = r._asdict()
        for k, v in d.items():
            if column_alias_prefix:
                if k.startswith(column_alias_prefix):
                    result_dict[k[len(column_alias_prefix) :]] = v
            else:
                result_dict[k] = v
        if additional_cols:
            result_dict.update(additional_cols)
        return cls.model_validate(result_dict)

    @classmethod
    def from_row_if_exists(
        cls: type[DBModelT], r: Row[Any], *, column_alias_prefix: str | None = None
    ) -> DBModelT | None:
        result_dict: dict[str, Any] = {}
        for k, v in r._asdict().items():
            if column_alias_prefix:
                if k.startswith(column_alias_prefix):
                    result_dict[k[len(column_alias_prefix) :]] = v
            else:
                result_dict[k] = v
        if all(v is None for v in result_dict.values()):
            return None
        return cls.model_validate(result_dict)


@dataclass
class MappedColumn:
    """Indicate if a field is mapped to a column."""

    is_json: bool = False
    is_array: bool = False


TypeT = TypeVar("TypeT", bound=Any)
Column = Annotated[TypeT, MappedColumn()]
JsonColumn = Annotated[TypeT, MappedColumn(is_json=True)]
ArrayColumn = Annotated[TypeT, MappedColumn(is_array=True)]


class ColumnFieldInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    mapped_column: MappedColumn
    field_info: FieldInfo


class TableModel(DBModel):
    """Base model for database tables."""

    table_name: ClassVar[str] = "unknown"
    schema_name: ClassVar[str] = "public"
    fq_table_name: ClassVar[str] = ""
    column_fields: ClassVar[dict[str, ColumnFieldInfo]] = {}
    ordered_column_names: ClassVar[tuple[str, ...]] = ()
    ordered_primary_keys: ClassVar[tuple[str, ...]] = ()
    is_base_table: ClassVar[bool] = False

    def model_post_init(self, __context: Any) -> None:
        if self.is_base_table:
            raise ValueError(f"Cannot instantiate base table model {self.__class__}")

    def insert_bind_params(self) -> dict[str, Any]:
        return {field_name: getattr(self, field_name) for field_name in self.column_fields}

    def primary_key_to_value(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.ordered_primary_keys}

    @classmethod
    def validate_contains_all_primary_keys(cls, columns: list[str] | dict[str, Any]) -> None:
        if set(cls.ordered_primary_keys) != set(columns):
            raise ValueError(
                f"primary keys {cls.ordered_primary_keys} must all be provided in {columns}",
            )

    @classmethod
    def validate_in_columns(cls, columns: list[str] | dict[str, Any]) -> None:
        for col in columns:
            if col not in cls.column_fields:
                raise ValueError(f"{col} is not a column for {cls.__name__}")

    @classmethod
    def get_json_columns(cls) -> list[str]:
        return [f for f, v in cls.column_fields.items() if v.mapped_column.is_json]

    @classmethod
    def array_columns(cls) -> list[str]:
        return [f for f, v in cls.column_fields.items() if v.mapped_column.is_array]

    @classmethod
    def get_column_names_with_alias(
        cls, *, table_alias: str, column_alias_prefix: str
    ) -> list[str]:
        return [
            f"{table_alias}.{col} AS {column_alias_prefix}{col}" for col in cls.ordered_column_names
        ]

    @classmethod
    def get_exposed_fields(cls) -> list[str]:
        return [field for field, _ in cls.model_fields.items()]

    @classmethod
    def get_table_name(cls) -> str:
        table_name = getattr(cls, "table_name", "unknown")
        if table_name == "unknown":
            raise ValueError(f"Table name is not set for {cls.__class__}")
        return table_name

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if cls.is_base_table:
            return
        if (not cls.table_name) or cls.table_name == "unknown":
            raise TypeError(f"table_name of class {cls.__name__} must be set!")
        if cls.schema_name:
            cls.fq_table_name = f"{cls.schema_name}.{cls.table_name}"
        else:
            cls.fq_table_name = cls.table_name
        cls.column_fields = cls.__get_column_fields()
        cls.__validate_primary_keys()
        cls.ordered_column_names = tuple(sorted(cls.column_fields.keys()))

    @classmethod
    def __validate_primary_keys(cls) -> None:
        if not cls.ordered_primary_keys:
            raise TypeError(
                f"ordered_primary_keys of class {cls.__name__} must be set!",
            )
        for pk in cls.ordered_primary_keys:
            if pk not in cls.column_fields:
                raise TypeError(
                    f"specified primary key ({pk}) doesn't have a matched column field defined!",
                )

    @classmethod
    def __get_column_fields(cls) -> dict[str, ColumnFieldInfo]:
        found: dict[str, ColumnFieldInfo] = {}
        for fn, info in cls.model_fields.items():
            column_metadata_list = [m for m in info.metadata if isinstance(m, MappedColumn)]
            if len(column_metadata_list) > 1:
                raise TypeError(
                    f"cannot provide more than 1 MappedColumn metadata to a field: {cls.__name__}.{fn}",
                )
            if len(column_metadata_list) == 1:
                found[fn] = ColumnFieldInfo(
                    mapped_column=column_metadata_list[0],
                    field_info=info,
                )
        return found

    @classmethod
    def __to_sql_column_list(
        cls,
        column_names: tuple[str, ...] | list[str],
    ) -> tuple[str, ...]:
        return column_names if isinstance(column_names, tuple) else tuple(column_names)

    @classmethod
    def __to_sql_column_param_list(
        cls,
        column_names: tuple[str, ...] | list[str],
    ) -> tuple[str, ...]:
        return tuple(f":{col}" for col in column_names)

    @classmethod
    def insert_sql_column_list(cls) -> tuple[str, ...]:
        return cls.__to_sql_column_list(cls.ordered_column_names)

    @classmethod
    def insert_sql_column_param_list(cls) -> tuple[str, ...]:
        return cls.__to_sql_column_param_list(cls.ordered_column_names)

    @classmethod
    def primary_key_column_list(cls) -> tuple[str, ...]:
        return cls.__to_sql_column_list(cls.ordered_primary_keys)


class SysTableModel(TableModel):
    """Table model with id and sys_updated_at fields."""

    is_base_table = True

    id: Column[UUID]
    sys_updated_at: Column[ZoneRequiredDateTime] = Field(default_factory=zoned_utc_now)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        cls.is_base_table = False
        super().__pydantic_init_subclass__(**kwargs)


class ColumnParity(BaseModel):
    model_config = ConfigDict(frozen=True)
    excluded_columns: frozenset[str] = Field(default_factory=frozenset)


class TableBoundedModel(
    AbstractUnsetAwareModel[AbstractUnsetAwareT], typing.Generic[AbstractUnsetAwareT]
):
    """Model bounded to a database table."""

    __table_model__: type[AbstractUnsetAwareT] = TableModel

    column_parity: ClassVar[ColumnParity | None] = None

    @classmethod
    def table_model(cls) -> type[AbstractUnsetAwareT]:
        return cls.__table_model__

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._validate_same_module_with_db_module()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls._populate_table_model()
        cls._validate_model_fields_against_table_model()

    @classmethod
    def _populate_table_model(cls) -> None:
        generic_origin = cls.__pydantic_generic_metadata__.get("origin", None)
        if not generic_origin:
            return
        if not issubclass(cls, generic_origin):
            raise TypeError(f"{cls.__name__} must be a subclass of {generic_origin})")
        generic_args = cls.__pydantic_generic_metadata__.get("args", ())
        if not generic_args:
            raise TypeError(f"{cls.__name__} must have generic args")
        first_generic_arg = generic_args[0]
        if inspect.isclass(first_generic_arg):
            if not issubclass(first_generic_arg, TableModel):
                raise TypeError(
                    f"{cls.__name__} must have a generic arg that is a subclass of TableModel",
                )
        elif not isinstance(first_generic_arg, TypeVar):
            raise TypeError(
                f"{cls.__name__} the generic arg can only be a TypeVar or a subclass of TableModel"
            )
        cls.__table_model__ = first_generic_arg

    @classmethod
    def _validate_same_module_with_db_module(cls) -> None:
        if isinstance(cls.__table_model__, TypeVar):
            return
        if cls.__table_model__.__module__ != cls.__module__:
            raise TypeError(
                f"table_model of class {cls.__name__} must be in the same module with the class.",
            )

    @classmethod
    def _validate_model_fields_against_table_model(cls) -> None:
        if isinstance(cls.__table_model__, TypeVar):
            return
        if cls.__table_model__ is TableModel:
            raise TypeError(
                f"table_model of class {cls.__name__} must be overridden to a subclass of DBModel",
            )
        if not issubclass(cls.__table_model__, TableModel):
            raise TypeError(
                f"table_model of class {cls.__name__} must be a subclass of DBModel",
            )
        table_column_fields: dict[str, ColumnFieldInfo] = cls.__table_model__.column_fields

        if cls.column_parity and (
            missing_columns := table_column_fields.keys()
            - cls.model_fields.keys()
            - cls.column_parity.excluded_columns
        ):
            raise TypeError(
                f"{missing_columns} are not declared to be in parity with source table model {cls.__table_model__.__name__}"
            )
        if cls.column_parity and (
            extra_columns := {
                extra_column
                for extra_column in cls.model_fields
                if extra_column in cls.column_parity.excluded_columns
            }
        ):
            raise TypeError(
                f"source table model {cls.__table_model__.__name__} has extra columns that are declared in cls.column_parity.extra_columns: {extra_columns}"
            )

        table_model_type_hints = typing.get_type_hints(cls.__table_model__)
        my_class_type_hints = typing.get_type_hints(cls)
        for f_name in cls.model_fields:
            if f_name not in table_column_fields:
                raise TypeError(
                    f"field {f_name} in {cls.__name__} is not found in {cls.__table_model__.__name__}",
                )
            my_field_type_hints = my_class_type_hints.get(f_name)

            if (
                typing.get_origin(my_field_type_hints) == typing.Union
                or type(my_field_type_hints) is types.UnionType
            ):
                my_field_type_hints = typing.get_args(my_field_type_hints) or (my_field_type_hints,)
            else:
                my_field_type_hints = (my_field_type_hints,)
            my_field_type_hints = tuple(th for th in my_field_type_hints if not is_unset_type(th))
            db_field_type_hints = table_model_type_hints.get(f_name)

            if (
                typing.get_origin(db_field_type_hints) == typing.Union
                or type(db_field_type_hints) is types.UnionType
            ):
                db_field_type_hints = typing.get_args(db_field_type_hints) or (db_field_type_hints,)
            else:
                db_field_type_hints = (db_field_type_hints,)
            if set(my_field_type_hints) - set(db_field_type_hints):
                raise TypeError(
                    f"field {f_name} in {cls.__name__} has different type from {cls.__table_model__.__name__}",
                    f"expected within {db_field_type_hints}, got {my_field_type_hints}",
                )

    def flatten_specified_values(self) -> dict[str, Any]:
        """Flatten the specified values of the model into a dictionary."""
        result: dict[str, Any] = {}
        for f_name in self.model_fields:
            if specified(f_value := getattr(self, f_name)):
                result[f_name] = f_value
        for cf_name in self.model_computed_fields:
            if specified(cf_value := getattr(self, cf_name)):
                result[cf_name] = cf_value
        return result


class ConditionalUpdateResult(BaseModel, typing.Generic[DBModelT]):
    record: DBModelT
    is_updated: bool
