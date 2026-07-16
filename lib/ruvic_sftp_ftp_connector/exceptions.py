"""Excepciones propias del conector SFTP/FTP.

Separan los tipos de fallo que el usuario debe distinguir: configuración
inválida, autenticación, red, seguridad (host key / ruta fuera del
directorio permitido), y datos (archivo/directorio inexistente, etc.).
"""


class SftpFtpConnectorError(Exception):
    """Error base del conector."""


class SftpFtpConfigError(SftpFtpConnectorError):
    """Configuración inválida: falta un campo requerido por el protocolo
    o modo de autenticación elegido."""


class SftpFtpAuthError(SftpFtpConnectorError):
    """Usuario/contraseña o clave privada inválidos, o el servidor rechazó
    la autenticación."""


class SftpFtpNetworkError(SftpFtpConnectorError):
    """No se pudo alcanzar el servidor (DNS, timeout, conexión rechazada)."""


class SftpFtpSecurityError(SftpFtpConnectorError):
    """La operación fue bloqueada por una protección de seguridad: la ruta
    solicitada intenta salir del directorio raíz permitido (base_path), o
    la huella digital del host SSH no coincide con la esperada (posible
    ataque man-in-the-middle)."""


class SftpFtpDataError(SftpFtpConnectorError):
    """La operación es válida pero el archivo/directorio no existe, o la
    operación falló por una razón propia del servidor remoto (permisos,
    espacio en disco, etc.)."""
