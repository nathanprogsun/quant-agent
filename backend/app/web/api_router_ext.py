"""Extended API Router with tenant validation."""

from collections.abc import Callable, Sequence
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, params, status
from fastapi.datastructures import Default
from fastapi.routing import APIRoute
from fastapi.types import DecoratedCallable, IncEx
from fastapi.utils import generate_unique_id
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute
from typing_extensions import Doc


def _require_tenant(request: Request) -> None:
    """Dependency that validates tenant context exists in request state."""
    if not getattr(request.state, "current_user_id", None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for tenanted endpoint",
        )
    if not getattr(request.state, "current_organization_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization context required",
        )


class APIRouterExt(APIRouter):
    """Extended APIRouter with automatic tenant validation.

    When user_organization_tenanted=True (default), endpoints require
    authenticated user with organization context.
    """

    def _build_tenanted_kwargs(
        self,
        kwargs: dict[str, Any],
        user_organization_tenanted: bool,
    ) -> dict[str, Any]:
        """Add tenant dependency if user_organization_tenanted is True."""
        if user_organization_tenanted:
            deps = list(kwargs.get("dependencies") or [])
            deps.append(Depends(_require_tenant))
            kwargs["dependencies"] = deps
        return kwargs

    def get(
        self,
        path: Annotated[str, Doc("The URL path to be used for this *path operation*.")],
        *,
        response_model: Annotated[Any, Doc("The type to use for the response.")] = Default(None),
        status_code: Annotated[
            int | None, Doc("The default status code to be used for the response.")
        ] = None,
        tags: Annotated[
            list[str | Enum] | None, Doc("A list of tags to be applied to the *path operation*.")
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc("A list of dependencies to be applied to the *path operation*."),
        ] = None,
        summary: Annotated[str | None, Doc("A summary for this *path operation*.")] = None,
        description: Annotated[str | None, Doc("A description for this *path operation*.")] = None,
        response_description: Annotated[
            str, Doc("The description for the default response.")
        ] = "Successful Response",
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc("Additional responses that could be returned by this *path operation*."),
        ] = None,
        deprecated: Annotated[bool | None, Doc("Mark this *path operation* as deprecated.")] = None,
        operation_id: Annotated[
            str | None, Doc("Custom operation ID to be used for this *path operation*.")
        ] = None,
        response_model_include: Annotated[
            IncEx | None,
            Doc(
                "Configuration passed to Pydantic to include only certain fields in the response data."
            ),
        ] = None,
        response_model_exclude: Annotated[
            IncEx | None,
            Doc("Configuration passed to Pydantic to exclude certain fields in the response data."),
        ] = None,
        response_model_by_alias: Annotated[
            bool,
            Doc(
                "Configuration passed to Pydantic to define if the response model should be serialized by alias when an alias is used."
            ),
        ] = True,
        response_model_exclude_unset: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_defaults: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_none: Annotated[
            bool, Doc("When True, fields set to None are omitted from the response.")
        ] = False,
        include_in_schema: Annotated[
            bool, Doc("Include this *path operation* in the generated OpenAPI schema.")
        ] = True,
        response_class: Annotated[
            type[Response], Doc("Response class to be used for this *path operation*.")
        ] = Default(JSONResponse),
        name: Annotated[
            str | None, Doc("Name for this *path operation*. Only used internally.")
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc("List of *path operations* that will be used as OpenAPI callbacks."),
        ] = None,
        openapi_extra: Annotated[
            dict[str, Any] | None,
            Doc("Extra metadata to be included in the OpenAPI schema for this *path operation*."),
        ] = None,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc("Customize the function used to generate unique IDs for the *path operations*."),
        ] = Default(generate_unique_id),
        user_organization_tenanted: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        kwargs = self._build_tenanted_kwargs(
            {"dependencies": dependencies},
            user_organization_tenanted,
        )
        return super().get(
            path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=kwargs.get("dependencies"),
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def post(
        self,
        path: Annotated[str, Doc("The URL path to be used for this *path operation*.")],
        *,
        response_model: Annotated[Any, Doc("The type to use for the response.")] = Default(None),
        status_code: Annotated[
            int | None, Doc("The default status code to be used for the response.")
        ] = None,
        tags: Annotated[
            list[str | Enum] | None, Doc("A list of tags to be applied to the *path operation*.")
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc("A list of dependencies to be applied to the *path operation*."),
        ] = None,
        summary: Annotated[str | None, Doc("A summary for this *path operation*.")] = None,
        description: Annotated[str | None, Doc("A description for this *path operation*.")] = None,
        response_description: Annotated[
            str, Doc("The description for the default response.")
        ] = "Successful Response",
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc("Additional responses that could be returned by this *path operation*."),
        ] = None,
        deprecated: Annotated[bool | None, Doc("Mark this *path operation* as deprecated.")] = None,
        operation_id: Annotated[
            str | None, Doc("Custom operation ID to be used for this *path operation*.")
        ] = None,
        response_model_include: Annotated[
            IncEx | None,
            Doc(
                "Configuration passed to Pydantic to include only certain fields in the response data."
            ),
        ] = None,
        response_model_exclude: Annotated[
            IncEx | None,
            Doc("Configuration passed to Pydantic to exclude certain fields in the response data."),
        ] = None,
        response_model_by_alias: Annotated[
            bool,
            Doc(
                "Configuration passed to Pydantic to define if the response model should be serialized by alias when an alias is used."
            ),
        ] = True,
        response_model_exclude_unset: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_defaults: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_none: Annotated[
            bool, Doc("When True, fields set to None are omitted from the response.")
        ] = False,
        include_in_schema: Annotated[
            bool, Doc("Include this *path operation* in the generated OpenAPI schema.")
        ] = True,
        response_class: Annotated[
            type[Response], Doc("Response class to be used for this *path operation*.")
        ] = Default(JSONResponse),
        name: Annotated[
            str | None, Doc("Name for this *path operation*. Only used internally.")
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc("List of *path operations* that will be used as OpenAPI callbacks."),
        ] = None,
        openapi_extra: Annotated[
            dict[str, Any] | None,
            Doc("Extra metadata to be included in the OpenAPI schema for this *path operation*."),
        ] = None,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc("Customize the function used to generate unique IDs for the *path operations*."),
        ] = Default(generate_unique_id),
        user_organization_tenanted: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        kwargs = self._build_tenanted_kwargs(
            {"dependencies": dependencies},
            user_organization_tenanted,
        )
        return super().post(
            path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=kwargs.get("dependencies"),
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def put(
        self,
        path: Annotated[str, Doc("The URL path to be used for this *path operation*.")],
        *,
        response_model: Annotated[Any, Doc("The type to use for the response.")] = Default(None),
        status_code: Annotated[
            int | None, Doc("The default status code to be used for the response.")
        ] = None,
        tags: Annotated[
            list[str | Enum] | None, Doc("A list of tags to be applied to the *path operation*.")
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc("A list of dependencies to be applied to the *path operation*."),
        ] = None,
        summary: Annotated[str | None, Doc("A summary for this *path operation*.")] = None,
        description: Annotated[str | None, Doc("A description for this *path operation*.")] = None,
        response_description: Annotated[
            str, Doc("The description for the default response.")
        ] = "Successful Response",
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc("Additional responses that could be returned by this *path operation*."),
        ] = None,
        deprecated: Annotated[bool | None, Doc("Mark this *path operation* as deprecated.")] = None,
        operation_id: Annotated[
            str | None, Doc("Custom operation ID to be used for this *path operation*.")
        ] = None,
        response_model_include: Annotated[
            IncEx | None,
            Doc(
                "Configuration passed to Pydantic to include only certain fields in the response data."
            ),
        ] = None,
        response_model_exclude: Annotated[
            IncEx | None,
            Doc("Configuration passed to Pydantic to exclude certain fields in the response data."),
        ] = None,
        response_model_by_alias: Annotated[
            bool,
            Doc(
                "Configuration passed to Pydantic to define if the response model should be serialized by alias when an alias is used."
            ),
        ] = True,
        response_model_exclude_unset: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_defaults: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_none: Annotated[
            bool, Doc("When True, fields set to None are omitted from the response.")
        ] = False,
        include_in_schema: Annotated[
            bool, Doc("Include this *path operation* in the generated OpenAPI schema.")
        ] = True,
        response_class: Annotated[
            type[Response], Doc("Response class to be used for this *path operation*.")
        ] = Default(JSONResponse),
        name: Annotated[
            str | None, Doc("Name for this *path operation*. Only used internally.")
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc("List of *path operations* that will be used as OpenAPI callbacks."),
        ] = None,
        openapi_extra: Annotated[
            dict[str, Any] | None,
            Doc("Extra metadata to be included in the OpenAPI schema for this *path operation*."),
        ] = None,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc("Customize the function used to generate unique IDs for the *path operations*."),
        ] = Default(generate_unique_id),
        user_organization_tenanted: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        kwargs = self._build_tenanted_kwargs(
            {"dependencies": dependencies},
            user_organization_tenanted,
        )
        return super().put(
            path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=kwargs.get("dependencies"),
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def patch(
        self,
        path: Annotated[str, Doc("The URL path to be used for this *path operation*.")],
        *,
        response_model: Annotated[Any, Doc("The type to use for the response.")] = Default(None),
        status_code: Annotated[
            int | None, Doc("The default status code to be used for the response.")
        ] = None,
        tags: Annotated[
            list[str | Enum] | None, Doc("A list of tags to be applied to the *path operation*.")
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc("A list of dependencies to be applied to the *path operation*."),
        ] = None,
        summary: Annotated[str | None, Doc("A summary for this *path operation*.")] = None,
        description: Annotated[str | None, Doc("A description for this *path operation*.")] = None,
        response_description: Annotated[
            str, Doc("The description for the default response.")
        ] = "Successful Response",
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc("Additional responses that could be returned by this *path operation*."),
        ] = None,
        deprecated: Annotated[bool | None, Doc("Mark this *path operation* as deprecated.")] = None,
        operation_id: Annotated[
            str | None, Doc("Custom operation ID to be used for this *path operation*.")
        ] = None,
        response_model_include: Annotated[
            IncEx | None,
            Doc(
                "Configuration passed to Pydantic to include only certain fields in the response data."
            ),
        ] = None,
        response_model_exclude: Annotated[
            IncEx | None,
            Doc("Configuration passed to Pydantic to exclude certain fields in the response data."),
        ] = None,
        response_model_by_alias: Annotated[
            bool,
            Doc(
                "Configuration passed to Pydantic to define if the response model should be serialized by alias when an alias is used."
            ),
        ] = True,
        response_model_exclude_unset: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_defaults: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_none: Annotated[
            bool, Doc("When True, fields set to None are omitted from the response.")
        ] = False,
        include_in_schema: Annotated[
            bool, Doc("Include this *path operation* in the generated OpenAPI schema.")
        ] = True,
        response_class: Annotated[
            type[Response], Doc("Response class to be used for this *path operation*.")
        ] = Default(JSONResponse),
        name: Annotated[
            str | None, Doc("Name for this *path operation*. Only used internally.")
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc("List of *path operations* that will be used as OpenAPI callbacks."),
        ] = None,
        openapi_extra: Annotated[
            dict[str, Any] | None,
            Doc("Extra metadata to be included in the OpenAPI schema for this *path operation*."),
        ] = None,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc("Customize the function used to generate unique IDs for the *path operations*."),
        ] = Default(generate_unique_id),
        user_organization_tenanted: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        kwargs = self._build_tenanted_kwargs(
            {"dependencies": dependencies},
            user_organization_tenanted,
        )
        return super().patch(
            path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=kwargs.get("dependencies"),
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )

    def delete(
        self,
        path: Annotated[str, Doc("The URL path to be used for this *path operation*.")],
        *,
        response_model: Annotated[Any, Doc("The type to use for the response.")] = Default(None),
        status_code: Annotated[
            int | None, Doc("The default status code to be used for the response.")
        ] = None,
        tags: Annotated[
            list[str | Enum] | None, Doc("A list of tags to be applied to the *path operation*.")
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc("A list of dependencies to be applied to the *path operation*."),
        ] = None,
        summary: Annotated[str | None, Doc("A summary for this *path operation*.")] = None,
        description: Annotated[str | None, Doc("A description for this *path operation*.")] = None,
        response_description: Annotated[
            str, Doc("The description for the default response.")
        ] = "Successful Response",
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc("Additional responses that could be returned by this *path operation*."),
        ] = None,
        deprecated: Annotated[bool | None, Doc("Mark this *path operation* as deprecated.")] = None,
        operation_id: Annotated[
            str | None, Doc("Custom operation ID to be used for this *path operation*.")
        ] = None,
        response_model_include: Annotated[
            IncEx | None,
            Doc(
                "Configuration passed to Pydantic to include only certain fields in the response data."
            ),
        ] = None,
        response_model_exclude: Annotated[
            IncEx | None,
            Doc("Configuration passed to Pydantic to exclude certain fields in the response data."),
        ] = None,
        response_model_by_alias: Annotated[
            bool,
            Doc(
                "Configuration passed to Pydantic to define if the response model should be serialized by alias when an alias is used."
            ),
        ] = True,
        response_model_exclude_unset: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_defaults: Annotated[
            bool, Doc("When True, default values are omitted from the response.")
        ] = False,
        response_model_exclude_none: Annotated[
            bool, Doc("When True, fields set to None are omitted from the response.")
        ] = False,
        include_in_schema: Annotated[
            bool, Doc("Include this *path operation* in the generated OpenAPI schema.")
        ] = True,
        response_class: Annotated[
            type[Response], Doc("Response class to be used for this *path operation*.")
        ] = Default(JSONResponse),
        name: Annotated[
            str | None, Doc("Name for this *path operation*. Only used internally.")
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc("List of *path operations* that will be used as OpenAPI callbacks."),
        ] = None,
        openapi_extra: Annotated[
            dict[str, Any] | None,
            Doc("Extra metadata to be included in the OpenAPI schema for this *path operation*."),
        ] = None,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc("Customize the function used to generate unique IDs for the *path operations*."),
        ] = Default(generate_unique_id),
        user_organization_tenanted: bool = True,
    ) -> Callable[[DecoratedCallable], DecoratedCallable]:
        kwargs = self._build_tenanted_kwargs(
            {"dependencies": dependencies},
            user_organization_tenanted,
        )
        return super().delete(
            path,
            response_model=response_model,
            status_code=status_code,
            tags=tags,
            dependencies=kwargs.get("dependencies"),
            summary=summary,
            description=description,
            response_description=response_description,
            responses=responses,
            deprecated=deprecated,
            operation_id=operation_id,
            response_model_include=response_model_include,
            response_model_exclude=response_model_exclude,
            response_model_by_alias=response_model_by_alias,
            response_model_exclude_unset=response_model_exclude_unset,
            response_model_exclude_defaults=response_model_exclude_defaults,
            response_model_exclude_none=response_model_exclude_none,
            include_in_schema=include_in_schema,
            response_class=response_class,
            name=name,
            callbacks=callbacks,
            openapi_extra=openapi_extra,
            generate_unique_id_function=generate_unique_id_function,
        )
