"""harga-pangan-dq: a live data-quality monitor for Indonesian strategic food prices."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("harga-pangan-dq")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"
