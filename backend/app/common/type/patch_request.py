"""UnsetAware type for Patch Requests."""

from collections.abc import Callable
from typing import (
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    TypedDict,
    TypeVar,
    Unpack,
    cast,
    final,
)

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WrapSerializer,
    model_serializer,
)
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import TypeIs

__all__ = [
    "UNSET",
    "AbstractUnsetAwareModel",
    "AbstractUnsetAwareT",
    "BasePatchRequest",
    "UnsetAware",
    "is_unset",
    "is_unset_type",
    "new_or_unset_if_same",
    "specified",
]

from pydantic_core import PydanticUndefined
from pydantic_core.core_schema import SerializationInfo

T = TypeVar("T")


class _UnsetKwargs(TypedDict):
    """TypedDict for __init_subclass__ kwargs to satisfy mypy strict mode."""


@final
class _Unset(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    def __init_subclass__(cls, **kwargs: Unpack[_UnsetKwargs]) -> None:
        super().__init_subclass__(**kwargs)
        raise TypeError("You cannot subclass _Unset")


UNSET: Final = _Unset()


def ensure_is_patch_request_subclass(v: Any, info: Any) -> Any:
    """Enforce UnsetAware fields are only used in subclasses of BasePatchRequest."""
    class_schema_title: str = info.config.get("title", "") if info.config else ""
    if BasePatchRequest._title_element not in class_schema_title:
        raise ValueError(
            "the field defined with UnsetAware must be used in a subclass of BasePatchRequest"
        )
    return v


def serialize_unset(v: Any, handler: Callable[[Any], Any], info: Any) -> Any:
    if isinstance(v, _Unset):
        return None
    return handler(v)


UnsetAware = Annotated[
    T | SkipJsonSchema[_Unset],
    Field(
        default_factory=lambda: UNSET,
        union_mode="smart",
    ),
    BeforeValidator(ensure_is_patch_request_subclass),
    WrapSerializer(serialize_unset),
]


def specified(val: UnsetAware[T]) -> TypeIs[T]:
    return not isinstance(val, _Unset)


def is_unset(val: Any) -> TypeIs[_Unset]:
    return isinstance(val, _Unset)


def is_unset_type(val: Any) -> bool:
    return val is _Unset


def new_or_unset_if_same(*, old: T, new: T | _Unset) -> T | _Unset:
    return new if (not is_unset(new)) and (new != old) else UNSET


AbstractUnsetAwareT = TypeVar("AbstractUnsetAwareT")


class AbstractUnsetAwareModel(BaseModel, Generic[AbstractUnsetAwareT]):
    _title_element: ClassVar[str] = "UnsetTypeAware"

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        title=_title_element,
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        this_cls_title = cls.model_config.get("title", cls.__name__) or ""
        cls.model_config["title"] = (
            f"{this_cls_title} ({AbstractUnsetAwareModel._title_element})"
            if AbstractUnsetAwareModel._title_element not in this_cls_title
            else this_cls_title
        )

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        fields = cls.model_fields

        for field_name, field_info in fields.items():
            if callable(field_info.default_factory) and (
                field_info.default is not PydanticUndefined
            ):
                default_factory_value = cast(Callable[[], Any], field_info.default_factory)()
                if default_factory_value != field_info.default:
                    raise TypeError(
                        f"there is default-factory defined for {field_name}, the factory "
                        f"vends values with type ({type(default_factory_value)}) "
                        "user shouldn't set default value vending different type "
                        f"({type(field_info.default)}) at the same time."
                    )

    def _find_unset_fields(self) -> set[str]:
        return {
            field_name
            for field_name in self.model_fields
            if is_unset(getattr(self, field_name, None))
        }

    @model_serializer(mode="wrap")
    def _custom_serialize_unset(
        self, handler: Callable[[Any], Any], info: SerializationInfo
    ) -> Any:
        """Ensure unset value is never serialized into dict or json."""
        interim = handler(self)
        unspecified_fields = self._find_unset_fields()
        for field_name in unspecified_fields:
            interim.pop(field_name, None)
        return interim


class BasePatchRequest(AbstractUnsetAwareModel[Any]):
    """
    Base class for PATCH requests with UnsetAware fields.

    See patch_request unit tests for usage examples and usage restrictions!
    """

    require_at_least_one_specified_field: ClassVar[bool] = False

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        if self.require_at_least_one_specified_field and not any(
            specified(getattr(self, field_name)) for field_name in self.model_fields
        ):
            raise ValueError("need at least one field to be specified")

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Intentionally set model dump to filter out unset fields for patching request."""
        kwargs["exclude_unset"] = True
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Intentionally set model dump to filter out unset fields for patching request."""
        kwargs["exclude_unset"] = True
        return super().model_dump_json(**kwargs)
