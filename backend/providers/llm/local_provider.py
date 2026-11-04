from .base import build_provider

def create(config=None):
    return build_provider(config) if config is not None else build_provider()
