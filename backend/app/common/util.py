from app.settings import get_settings


def is_dev_env() -> bool:
    return get_settings().environment in ("development", "dev")


def is_prod_env() -> bool:
    return get_settings().environment == "production"


def is_local_env() -> bool:
    return get_settings().environment == "local"


def is_staging_env() -> bool:
    return get_settings().environment == "staging"
