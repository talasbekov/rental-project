import os

def get_env(var_name: str, default=None, required: bool = False):
    value = os.environ.get(var_name, default)
    if required and value in (None, ""):
        raise ImproperlyConfigured(f"Missing required environment variable: {var_name}")
    return value
