"""Prueba de conexión estándar del conector sftp_ftp.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_SFTP_FTP_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Verifica el acceso al servidor usando las env vars RUVIC_SFTP_FTP_*."""
    try:
        from ruvic_sftp_ftp_connector import (
            SftpFtpAuthError,
            SftpFtpClient,
            SftpFtpDataError,
            SftpFtpNetworkError,
            SftpFtpSecurityError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-sftp-ftp-connector no está instalada. "
            "Instala con: pip install git+https://github.com/tu-org/"
            "conector-sftp-ftp.git#subdirectory=lib",
        )

    try:
        client = SftpFtpClient()  # valida config y credenciales del modo detectado
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except SftpFtpAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except SftpFtpNetworkError as exc:
        return False, f"Error de red: {exc}"
    except SftpFtpSecurityError as exc:
        return False, f"Bloqueado por seguridad: {exc}"
    except SftpFtpDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return True, f"Conexión exitosa a {client.config.host} ({client.config.protocol})"


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
