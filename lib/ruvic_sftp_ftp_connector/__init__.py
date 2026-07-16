"""Conector Ruvic para intercambio de archivos por SFTP y FTP/FTPS."""

from .client import SftpFtpClient
from .config import ENV_PREFIX, SftpFtpConfig
from .exceptions import (
    SftpFtpAuthError,
    SftpFtpConfigError,
    SftpFtpConnectorError,
    SftpFtpDataError,
    SftpFtpNetworkError,
    SftpFtpSecurityError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "SftpFtpAuthError",
    "SftpFtpClient",
    "SftpFtpConfig",
    "SftpFtpConfigError",
    "SftpFtpConnectorError",
    "SftpFtpDataError",
    "SftpFtpNetworkError",
    "SftpFtpSecurityError",
    "setup_logging",
]

__version__ = "1.0.0"
