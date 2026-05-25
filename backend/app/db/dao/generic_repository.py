"""Generic repository with standard CRUD operations."""

from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from app.common.exception import ResourceNotFoundError
from app.db.dbengine.core import DatabaseEngine
from app.db.models.core.base import (
    ConditionalUpdateResult,
    TableBoundedModel,
    TableModel,
)

TableModelT = TypeVar("TableModelT", bound=TableModel)

# Type alias for column condition values
ColumnConditionValueType = str | int | float | bool | None | datetime


class GenericRepository:
    """Generic repository providing basic CRUD db queries.

    Concrete repositories should extend this class and add
    domain-specific methods (create, update, delete, find_by_*, etc.).

    Args:
        engine: DatabaseEngine instance for executing queries.
    """

    def __init__(self, engine: DatabaseEngine) -> None:
        self.engine = engine

    @staticmethod
    def _get_table_model_upsert_pk_stmt(
        instance: TableModelT,
        *,
        exclude_columns_from_update: list[str] | None = None,
    ):
        instance.validate_in_columns(exclude_columns_from_update or [])

        all_columns: tuple[str, ...] = instance.insert_sql_column_list()

        stmt_text = f"""insert into {instance.fq_table_name}
        ({", ".join([f'"{c}"' for c in all_columns])})
        values
        ({", ".join(instance.insert_sql_column_param_list())})
        """
        param_kwargs: dict[str, Any] = instance.insert_bind_params()

        primary_keys = instance.primary_key_column_list()
        excluded_columns = list(primary_keys)
        if exclude_columns_from_update:
            excluded_columns += exclude_columns_from_update
        update_columns = [c for c in all_columns if c not in excluded_columns]
        update_values = tuple(f":{col}" for col in update_columns)

        conflict_targets = f"({', '.join(primary_keys)})"
        updates = ", ".join(
            [f"{t[0]} = {t[1]}" for t in zip(update_columns, update_values, strict=True)]
        )
        on_conflict_stmt = f"{stmt_text} on conflict {conflict_targets}"
        do_stmt = (
            f"{on_conflict_stmt} do update set {updates}"
            if updates
            else f"{on_conflict_stmt} do nothing"
        )
        stmt_text_with_return = f"{do_stmt} returning *"

        json_params = [bindparam(f, type_=JSONB) for f in instance.get_json_columns()]

        return text(stmt_text_with_return).bindparams(
            *json_params,
            **param_kwargs,
        )

    @staticmethod
    def _get_table_model_standard_insert_stmt(
        instance: TableModelT,
        *,
        on_conflict_do_nothing_target_columns: list[str] | None = None,
        on_conflict_do_nothing_conditional_columns: (
            dict[
                str,
                ColumnConditionValueType,
            ]
            | None
        ) = None,
    ):
        """Build a standard insert statement with optional ON CONFLICT DO NOTHING.

        Args:
            instance: The model instance to insert.
            on_conflict_do_nothing_target_columns: Columns for conflict target.
            on_conflict_do_nothing_conditional_columns: Conditional columns for WHERE clause.

        Returns:
            SQLAlchemy text statement with bind params.
        """
        instance.validate_in_columns(on_conflict_do_nothing_target_columns or [])
        instance.validate_in_columns(on_conflict_do_nothing_conditional_columns or {})

        columns: tuple[str, ...] = instance.insert_sql_column_list()

        stmt_text = f"""insert into {instance.fq_table_name}
        ({", ".join([f'"{c}"' for c in columns])})
        values
        ({", ".join(instance.insert_sql_column_param_list())})
        """
        param_kwargs: dict[str, Any] = instance.insert_bind_params()

        if on_conflict_do_nothing_target_columns:
            quoted_cols = ['"' + c + '"' for c in on_conflict_do_nothing_target_columns]
            conflict_targets = f"({', '.join(quoted_cols)})"
            stmt_text = f"{stmt_text} on conflict {conflict_targets}"
            if on_conflict_do_nothing_conditional_columns:
                conflict_wheres = [
                    f'"{k}" is null' if v is None else f'"{k}" = :cf_{k}'
                    for k, v in on_conflict_do_nothing_conditional_columns.items()
                ]
                conflict_wheres_clause = f"where {' and '.join(conflict_wheres)}"
                conflict_where_params = {
                    f"cf_{k}": v
                    for k, v in on_conflict_do_nothing_conditional_columns.items()
                    if v is not None
                }
                param_kwargs.update(conflict_where_params)
                stmt_text = f"{stmt_text} {conflict_wheres_clause} do nothing"
            else:
                stmt_text = f"{stmt_text} do nothing"

        stmt_text_with_return = f"{stmt_text} returning *"

        json_params = [bindparam(f, type_=JSONB) for f in instance.get_json_columns()]

        return text(stmt_text_with_return).bindparams(
            *json_params,
            **param_kwargs,
        )

    async def insert(self, instance: TableModelT) -> TableModelT:
        """Insert a non-existed instance into table."""
        stmt = GenericRepository._get_table_model_standard_insert_stmt(instance)
        row = await self.engine.one(stmt)
        return instance.from_row(row)

    async def upsert_pk(
        self,
        instance: TableModelT,
        *,
        exclude_columns_from_update: list[str] | None = None,
    ) -> TableModelT | None:
        stmt = GenericRepository._get_table_model_upsert_pk_stmt(
            instance, exclude_columns_from_update=exclude_columns_from_update
        )
        row = await self.engine.at_most_one(stmt)
        return instance.from_row(row) if row else None

    async def upsert_unique_target_columns(
        self,
        instance: TableModelT,
        *,
        unique_target_columns: list[str],
        exclude_columns_from_update: list[str] | None = None,
    ) -> TableModelT | None:
        """Upsert based on unique target columns instead of primary key.

        Args:
            instance: The model instance to upsert.
            unique_target_columns: List of column names that form a unique constraint.
            exclude_columns_from_update: Columns to exclude from update on conflict.

        Returns:
            The upserted instance or None if no row was returned.
        """
        instance.validate_in_columns(unique_target_columns)
        instance.validate_in_columns(exclude_columns_from_update or [])

        all_columns: tuple[str, ...] = instance.insert_sql_column_list()

        stmt_text = f"""insert into {instance.fq_table_name}
        ({", ".join([f'"{c}"' for c in all_columns])})
        values
        ({", ".join(instance.insert_sql_column_param_list())})
        """
        param_kwargs: dict[str, Any] = instance.insert_bind_params()

        excluded_columns = list(unique_target_columns)
        if exclude_columns_from_update:
            excluded_columns += exclude_columns_from_update
        update_columns = [c for c in all_columns if c not in excluded_columns]
        update_values = tuple(f":{col}" for col in update_columns)

        quoted_cols = ['"' + c + '"' for c in unique_target_columns]
        conflict_targets = f"({', '.join(quoted_cols)})"
        updates = ", ".join(
            [f"{t[0]} = {t[1]}" for t in zip(update_columns, update_values, strict=True)]
        )
        on_conflict_stmt = f"{stmt_text} on conflict {conflict_targets}"
        do_stmt = (
            f"{on_conflict_stmt} do update set {updates}"
            if updates
            else f"{on_conflict_stmt} do nothing"
        )
        stmt_text_with_return = f"{do_stmt} returning *"

        json_params = [bindparam(f, type_=JSONB) for f in instance.get_json_columns()]

        stmt = text(stmt_text_with_return).bindparams(
            *json_params,
            **param_kwargs,
        )
        row = await self.engine.at_most_one(stmt)
        return instance.from_row(row) if row else None

    async def insert_or_none(
        self,
        instance: TableModelT,
        *,
        on_conflict_do_nothing_target_columns: list[str],
        on_conflict_do_nothing_conditional_columns: (
            dict[
                str,
                ColumnConditionValueType,
            ]
            | None
        ) = None,
    ) -> TableModelT | None:
        """Insert a non-existed instance into table with ON CONFLICT DO NOTHING.

        Uses ON CONFLICT DO NOTHING and returns None if no row was inserted
        (i.e., when a conflict occurs on the target columns).

        Args:
            instance: The model instance to insert.
            on_conflict_do_nothing_target_columns: List of column names that form
                a unique constraint for conflict detection.
            on_conflict_do_nothing_conditional_columns: Optional conditional columns
                for the WHERE clause of ON CONFLICT DO NOTHING.
                Example: {"status": "active"} means "do nothing only if status='active'".

        Returns:
            The inserted instance if successful, or None if a conflict was detected
            and nothing was inserted.

        Example:
            # Insert user only if email doesn't exist
            user = UserModel(email="test@example.com", name="Test")
            result = await repo.insert_or_none(
                user,
                on_conflict_do_nothing_target_columns=["email"],
            )
            if result is None:
                # User with this email already exists
                pass
        """
        stmt = GenericRepository._get_table_model_standard_insert_stmt(
            instance,
            on_conflict_do_nothing_target_columns=on_conflict_do_nothing_target_columns,
            on_conflict_do_nothing_conditional_columns=on_conflict_do_nothing_conditional_columns,
        )
        row = await self.engine.at_most_one(stmt)
        return instance.from_row(row) if row else None

    async def find_by_primary_key(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool | None = True,
        **primary_key_to_value: Any,
    ) -> TableModelT | None:
        """Find a pre-existed row by its table's primary key(s)."""
        for pk in table_model.ordered_primary_keys:
            if pk not in primary_key_to_value:
                raise ValueError(
                    f"primary key ({pk}) of table ({table_model.table_name}) need to be specified!"
                )

        pk_columns = table_model.primary_key_column_list()
        pk_where = " and ".join([f"{pk_col} = :{pk_col}" for pk_col in pk_columns])
        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )
        stmt = text(
            f"""
            select * from {table_model.fq_table_name}
            where {pk_where} {where_filter_deleted} {where_filter_archived}
            """,
        ).bindparams(**primary_key_to_value)

        row = await self.engine.at_most_one(stmt)
        return table_model.from_row(row) if row else None

    async def find_by_primary_key_or_fail(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool | None = True,
        **primary_key_to_value: Any,
    ) -> TableModelT:
        result = await self.find_by_primary_key(
            table_model=table_model,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            **primary_key_to_value,
        )
        if not result:
            raise ResourceNotFoundError(
                f"Record not found for table {table_model.table_name} "
                f"with primary key {primary_key_to_value}",
            )
        return result

    async def find_by_tenanted_primary_key(
        self,
        table_model: type[TableModelT],
        *,
        organization_id: UUID,
        exclude_deleted_or_archived: bool | None = True,
        **primary_key_to_value: Any,
    ) -> TableModelT | None:
        """Find by primary key with tenant filter."""
        for pk in table_model.ordered_primary_keys:
            if pk not in primary_key_to_value:
                raise ValueError(
                    f"primary key ({pk}) of table ({table_model.table_name}) need to be specified!"
                )

        if "organization_id" not in table_model.column_fields:
            raise ValueError(
                f"organization_id is not a column in table {table_model.table_name}",
            )

        pk_columns = table_model.primary_key_column_list()
        pk_where = " and ".join([f"{pk_col} = :{pk_col}" for pk_col in pk_columns])
        org_id_filter = "and organization_id = :organization_id"
        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )
        stmt = (
            text(
                f"""
            select * from {table_model.fq_table_name}
            where {pk_where} {org_id_filter} {where_filter_deleted} {where_filter_archived}
            """,
            )
            .bindparams(**primary_key_to_value)
            .bindparams(organization_id=organization_id)
        )

        row = await self.engine.at_most_one(stmt)
        return table_model.from_row(row) if row else None

    async def find_by_tenanted_primary_key_or_fail(
        self,
        table_model: type[TableModelT],
        *,
        organization_id: UUID,
        exclude_deleted_or_archived: bool | None = True,
        **primary_key_to_value: Any,
    ) -> TableModelT:
        """Find by primary key with tenant filter, or raise ResourceNotFoundError."""
        result = await self.find_by_tenanted_primary_key(
            table_model=table_model,
            organization_id=organization_id,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            **primary_key_to_value,
        )
        if not result:
            raise ResourceNotFoundError(
                f"Record not found for table {table_model.table_name} "
                f"with primary key {primary_key_to_value} and organization_id {organization_id}",
            )
        return result

    async def _find_by_column_values(
        self,
        table_model: type[TableModelT],
        *,
        unique: bool = False,
        exclude_deleted_or_archived: bool | None = True,
        **column_to_query: Any,
    ) -> list[TableModelT]:
        table_model.validate_in_columns(column_to_query)
        column_where = " and ".join(
            [
                f"{column_name} = :{column_name}"
                if column_value is not None
                else f"{column_name} is null"
                for column_name, column_value in column_to_query.items()
            ],
        )

        column_to_query_not_none = {k: v for k, v in column_to_query.items() if v is not None}

        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )
        stmt = text(
            f"""select * from {table_model.fq_table_name} where {column_where}
                {where_filter_deleted} {where_filter_archived}""",
        ).bindparams(**column_to_query_not_none)

        if unique:
            row = await self.engine.at_most_one(stmt)
            rows = [row] if row else []
        else:
            rows = list(await self.engine.all(stmt))

        return [table_model.from_row(row) for row in rows]

    async def _find_unique_by_column_values(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool = True,
        **column_to_query: Any,
    ) -> TableModelT | None:
        results = await self._find_by_column_values(
            table_model=table_model,
            unique=True,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            **column_to_query,
        )
        return results[0] if results else None

    async def _find_unique_by_column_values_or_fail(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool = True,
        **column_to_query: Any,
    ) -> TableModelT:
        """Find a unique row by column values, or raise ResourceNotFoundError.

        Args:
            table_model: The table model class.
            exclude_deleted_or_archived: Whether to exclude deleted/archived records.
            **column_to_query: Column name to value mappings.

        Returns:
            The found model instance.

        Raises:
            ResourceNotFoundError: If no record is found or multiple records exist.
        """
        results = await self._find_by_column_values(
            table_model=table_model,
            unique=True,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            **column_to_query,
        )
        if not results:
            raise ResourceNotFoundError(
                f"Record not found for table {table_model.table_name} "
                f"with columns {column_to_query}",
            )
        return results[0]

    async def _find_all(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool | None = True,
    ) -> list[TableModelT]:
        """Find all rows in the table.

        Args:
            table_model: The table model class.
            exclude_deleted_or_archived: Whether to exclude deleted/archived records.

        Returns:
            List of all found model instances.
        """
        where_filter_deleted = (
            "where (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )

        stmt = text(
            f"""select * from {table_model.fq_table_name}
                {where_filter_deleted} {where_filter_archived}""",
        )

        rows = await self.engine.all(stmt)
        return [table_model.from_row(row) for row in rows]

    async def _update_by_column_values_stmt(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool | None = False,
        column_value_to_query: dict[str, Any],
        column_to_update: dict[str, Any] | TableBoundedModel[TableModelT],
    ):
        if isinstance(column_to_update, TableBoundedModel):
            if not issubclass(table_model, column_to_update.table_model()):
                raise ValueError(
                    f"UpdateModel ({column_to_update}) is not for table ({table_model.table_name}).",
                )
            column_to_update = column_to_update.flatten_specified_values()

        table_model.validate_in_columns(column_value_to_query)
        table_model.validate_in_columns(column_to_update)

        where_filter_deleted = (
            " and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )

        column_where = " and ".join(
            [
                f"{column_name} = :{column_name}"
                if column_value is not None
                else f"{column_name} is null"
                for column_name, column_value in column_value_to_query.items()
            ],
        )

        columns_to_update_set = ", ".join(
            [f"{k} = :{k}" for k in column_to_update],
        )

        columns_update_param: dict[str, Any] = {}
        json_params: list = []
        model_json_column_names = table_model.get_json_columns()
        for col_name, update_value in column_to_update.items():
            columns_update_param[col_name] = update_value
            if col_name in model_json_column_names:
                json_params.append(bindparam(col_name, type_=JSONB))

        column_to_query_not_none = {k: v for k, v in column_value_to_query.items() if v is not None}
        return text(
            f"""
                    update {table_model.fq_table_name}
                    set {columns_to_update_set}
                    where {column_where}{where_filter_deleted}
                    returning *
                    """,
        ).bindparams(*json_params, **column_to_query_not_none, **columns_update_param)

    @staticmethod
    def _update_by_primary_key_stmt(
        table_model: type[TableModelT],
        *,
        primary_key_to_value: dict[str, Any],
        column_to_update: dict[str, Any],
        exclude_deleted_or_archived: bool | None = True,
    ) -> Any:
        """Build an update statement by primary key (static method).

        Args:
            table_model: The table model class.
            primary_key_to_value: Primary key column names to values.
            column_to_update: Columns and their new values.
            exclude_deleted_or_archived: Whether to exclude deleted/archived records.

        Returns:
            SQLAlchemy statement object.
        """
        table_model.validate_contains_all_primary_keys(primary_key_to_value)
        table_model.validate_in_columns(column_to_update)

        pk_columns = table_model.primary_key_column_list()
        pk_where = " and ".join([f"{pk_col} = :{pk_col}" for pk_col in pk_columns])

        columns_to_update_set = ", ".join(
            [f"{k} = :u_{k}" for k in column_to_update],
        )

        columns_update_param: dict[str, Any] = {f"u_{k}": v for k, v in column_to_update.items()}
        json_params = [
            bindparam(f"u_{col}", type_=JSONB)
            for col in column_to_update
            if col in table_model.get_json_columns()
        ]

        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )

        return text(
            f"""
                update {table_model.fq_table_name}
                set {columns_to_update_set}
                where {pk_where} {where_filter_deleted} {where_filter_archived}
                returning *
                """,
        ).bindparams(*json_params, **primary_key_to_value, **columns_update_param)

    async def update_by_primary_key(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool | None = True,
        primary_key_to_value: dict[str, Any],
        column_to_update: dict[str, Any] | TableBoundedModel[TableModelT],
    ) -> TableModelT | None:
        """Update a pre-existed row by its table's primary key(s)."""
        if isinstance(column_to_update, TableBoundedModel):
            column_to_update = column_to_update.flatten_specified_values()

        stmt = self._update_by_primary_key_stmt(
            table_model,
            primary_key_to_value=primary_key_to_value,
            column_to_update=column_to_update,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
        )

        row = await self.engine.at_most_one(stmt)
        return table_model.from_row(row) if row else None

    async def update_by_tenanted_primary_key(
        self,
        table_model: type[TableModelT],
        *,
        organization_id: UUID,
        exclude_deleted_or_archived: bool | None = True,
        primary_key_to_value: dict[str, Any],
        column_to_update: dict[str, Any] | TableBoundedModel[TableModelT],
    ) -> TableModelT | None:
        """Update a pre-existed row by its table's primary key(s) and organization_id."""
        if isinstance(column_to_update, TableBoundedModel):
            column_to_update = column_to_update.flatten_specified_values()

        table_model.validate_contains_all_primary_keys(primary_key_to_value)
        table_model.validate_in_columns(column_to_update)

        pk_columns = table_model.primary_key_column_list()
        pk_where = " and ".join([f"{pk_col} = :{pk_col}" for pk_col in pk_columns])

        columns_to_update_set = ", ".join(
            [f"{k} = :u_{k}" for k in column_to_update],
        )

        columns_update_param: dict[str, Any] = {f"u_{k}": v for k, v in column_to_update.items()}
        json_params = [
            bindparam(f"u_{col}", type_=JSONB)
            for col in column_to_update
            if col in table_model.get_json_columns()
        ]

        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )

        stmt = text(
            f"""
            update {table_model.fq_table_name}
            set {columns_to_update_set}
            where {pk_where} and organization_id=:organization_id {where_filter_deleted} {where_filter_archived}
            returning *
            """,
        ).bindparams(
            *json_params,
            **primary_key_to_value,
            organization_id=organization_id,
            **columns_update_param,
        )

        row = await self.engine.at_most_one(stmt)
        return table_model.from_row(row) if row else None

    async def conditionally_update_by_tenanted_primary_key_or_get(
        self,
        table_model: type[TableModelT],
        *,
        organization_id: UUID,
        primary_key_to_value: dict[str, Any],
        conditional_column: str,
        expected_value: Any,
        column_to_update: dict[str, Any] | TableBoundedModel[TableModelT],
        exclude_deleted_or_archived: bool | None = True,
    ) -> ConditionalUpdateResult[TableModelT]:
        """Conditionally update a row by primary key and tenant, or return current record.

        This method updates a record only if the conditional_column matches expected_value.
        If the condition is not met, it returns the current record without modification.

        Args:
            table_model: The table model class.
            organization_id: The organization UUID.
            primary_key_to_value: Primary key column names to values.
            conditional_column: Column name to check for conditional update.
            expected_value: Expected value in conditional_column for update to proceed.
            column_to_update: Columns and their new values if condition is met.
            exclude_deleted_or_archived: Whether to exclude deleted/archived records.

        Returns:
            ConditionalUpdateResult containing the record and whether it was updated.
        """
        if isinstance(column_to_update, TableBoundedModel):
            column_to_update = column_to_update.flatten_specified_values()

        table_model.validate_contains_all_primary_keys(primary_key_to_value)
        table_model.validate_in_columns([conditional_column])
        table_model.validate_in_columns(column_to_update)

        pk_columns = table_model.primary_key_column_list()
        pk_where = " and ".join([f"{pk_col} = :{pk_col}" for pk_col in pk_columns])

        columns_to_update_set = ", ".join(
            [f"{k} = :u_{k}" for k in column_to_update],
        )

        columns_update_param: dict[str, Any] = {f"u_{k}": v for k, v in column_to_update.items()}
        json_params = [
            bindparam(f"u_{col}", type_=JSONB)
            for col in column_to_update
            if col in table_model.get_json_columns()
        ]

        where_filter_deleted = (
            "and (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else ""
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )

        stmt = text(
            f"""
            update {table_model.fq_table_name}
            set {columns_to_update_set}
            where {pk_where}
              and organization_id=:organization_id
              and {conditional_column} = :expected_value
              {where_filter_deleted} {where_filter_archived}
            returning *
            """,
        ).bindparams(
            *json_params,
            **primary_key_to_value,
            organization_id=organization_id,
            expected_value=expected_value,
            **columns_update_param,
        )

        row = await self.engine.at_most_one(stmt)

        if row:
            return ConditionalUpdateResult(
                record=table_model.from_row(row),
                is_updated=True,
            )

        # Condition not met, return current record
        current_record = await self.find_by_tenanted_primary_key(
            table_model=table_model,
            organization_id=organization_id,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            **primary_key_to_value,
        )

        if current_record:
            return ConditionalUpdateResult(
                record=current_record,
                is_updated=False,
            )

        raise ResourceNotFoundError(
            f"Record not found for table {table_model.table_name} "
            f"with primary key {primary_key_to_value} and organization_id {organization_id}",
        )

    async def update_instance(
        self, instance: TableModelT, exclude_deleted_or_archived: bool = True
    ) -> TableModelT | None:
        """Update a pre-existed row by its table's primary key(s)."""
        return await self.update_by_primary_key(
            table_model=type(instance),
            primary_key_to_value=instance.primary_key_to_value(),
            column_to_update=instance.model_dump(
                exclude=set(instance.ordered_primary_keys),
            ),
            exclude_deleted_or_archived=exclude_deleted_or_archived,
        )

    async def _update_by_column_values(
        self,
        table_model: type[TableModelT],
        *,
        exclude_deleted_or_archived: bool = True,
        column_value_to_query: dict[str, Any],
        column_to_update: dict[str, Any] | TableBoundedModel[TableModelT],
        unique: bool = False,
    ) -> list[TableModelT]:
        stmt = await self._update_by_column_values_stmt(
            table_model,
            exclude_deleted_or_archived=exclude_deleted_or_archived,
            column_value_to_query=column_value_to_query,
            column_to_update=column_to_update,
        )

        if unique:
            row = await self.engine.at_most_one(stmt)
            unique_rows = [row] if row else []
            return [table_model.from_row(row) for row in unique_rows]
        rows = await self.engine.all(stmt)
        return [table_model.from_row(row) for row in rows]

    async def find_all(
        self,
        table_model: type[TableModelT],
        *,
        limit: int = 100,
        offset: int = 0,
        exclude_deleted_or_archived: bool | None = True,
    ) -> list[TableModelT]:
        """Find all rows with pagination.

        Args:
            table_model: The table model class.
            limit: Maximum number of results.
            offset: Number of rows to skip.
            exclude_deleted_or_archived: Whether to exclude deleted/archived records.

        Returns:
            List of model instances.
        """
        where_filter_deleted = (
            "where (deleted_at is null or deleted_at > current_timestamp)"
            if (exclude_deleted_or_archived and "deleted_at" in table_model.column_fields)
            else "where 1=1"
        )
        where_filter_archived = (
            "and (archived_at is null or archived_at > current_timestamp)"
            if (exclude_deleted_or_archived and "archived_at" in table_model.column_fields)
            else ""
        )

        stmt = text(
            f"""select * from {table_model.fq_table_name}
                {where_filter_deleted} {where_filter_archived}
                limit :limit offset :offset""",
        ).bindparams(limit=limit, offset=offset)

        rows = await self.engine.all(stmt)
        return [table_model.from_row(row) for row in rows]
