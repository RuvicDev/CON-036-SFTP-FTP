"""Cliente para intercambiar archivos por SFTP o FTP/FTPS.

Capacidades:
- list_directory():  listar el contenido de un directorio remoto.
- upload_file():     subir un archivo (desde bytes/texto en memoria).
- download_file():   descargar un archivo (retorna su contenido en bytes).
- move_file():       mover/renombrar un archivo remoto.
- delete_file():     eliminar un archivo remoto.

⚠️ A diferencia de la mayoría de conectores de Ruvic, este SÍ permite
eliminar archivos — es parte del alcance pedido para este conector.

Protecciones de seguridad incorporadas:
- Todas las rutas se resuelven dentro de un directorio raíz configurable
  (`base_path`, por defecto "/"). Cualquier intento de "escapar" con
  rutas tipo "../../otra_carpeta" se rechaza (protección de path
  traversal, equivalente en espíritu a la restricción de dominio del
  conector HTTP Genérico).
- SFTP verifica la huella digital del servidor (host key) contra la
  configurada en `host_key_fingerprint`, si se proporcionó — evita
  ataques man-in-the-middle. Si no se configura, se acepta con una
  advertencia registrada en el log (Trust On First Use), igual que hace
  un cliente SSH interactivo la primera vez que te conectas a un host.

Autenticación: usuario/contraseña o clave privada SSH (SFTP), o usuario/
contraseña con FTP/FTPS opcional. Las credenciales SIEMPRE provienen de
variables de entorno RUVIC_SFTP_FTP_* (ver config.SftpFtpConfig.from_env).
Prohibido hardcodearlas.
"""

from __future__ import annotations

import base64
import ftplib
import hashlib
import io
import posixpath
import socket
from typing import Any

import paramiko

from .config import SftpFtpConfig
from .exceptions import (
    SftpFtpAuthError,
    SftpFtpDataError,
    SftpFtpNetworkError,
    SftpFtpSecurityError,
)
from .logging_utils import get_logger


class _PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Política de verificación de host key: si se configuró una huella
    esperada, la exige exacta; si no, acepta con advertencia (TOFU)."""

    def __init__(self, expected_fingerprint: str, logger) -> None:
        self.expected_fingerprint = expected_fingerprint
        self.logger = logger

    def missing_host_key(self, client, hostname, key) -> None:
        actual = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        if self.expected_fingerprint:
            if actual != self.expected_fingerprint:
                raise SftpFtpSecurityError(
                    f"La huella digital del host {hostname!r} no coincide con la "
                    f"configurada. Esperada: {self.expected_fingerprint}, recibida: "
                    f"{actual}. Esto puede indicar un ataque man-in-the-middle — "
                    "la conexión se rechazó por seguridad."
                )
            return
        self.logger.warning(
            "Aceptando la clave del host %s sin verificar (primera conexión, TOFU). "
            "Huella recibida: %s. Para verificarla en conexiones futuras, configura "
            "host_key_fingerprint con este valor.",
            hostname, actual,
        )


def _load_private_key(key_text: str, passphrase: str | None):
    """Intenta parsear una clave privada probando los tipos soportados."""
    key_classes = (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey)
    last_error: Exception | None = None
    for key_cls in key_classes:
        try:
            return key_cls.from_private_key(io.StringIO(key_text), password=passphrase or None)
        except Exception as exc:  # noqa: BLE001 - probamos varios tipos a propósito
            last_error = exc
            continue
    raise SftpFtpAuthError(
        f"No se pudo interpretar la clave privada (probados Ed25519/RSA/ECDSA/DSS): {last_error}"
    )


class SftpFtpClient:
    """Cliente para SFTP o FTP/FTPS, según cómo se configuró el conector.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_SFTP_FTP_* (comportamiento estándar
            en el runtime de la plataforma).

    Ejemplo:
        >>> client = SftpFtpClient()  # lee RUVIC_SFTP_FTP_* del entorno
        >>> client.list_directory("/reportes")
        [{'name': 'ventas.csv', 'path': '/reportes/ventas.csv', 'size': 2048, 'is_directory': False, ...}]
    """

    def __init__(self, config: SftpFtpConfig | None = None) -> None:
        self.config = config or SftpFtpConfig.from_env()
        self._logger = get_logger()

    # ------------------------------------------------------------------ #
    # Resolución segura de rutas (protección de path traversal)
    # ------------------------------------------------------------------ #

    def _resolve_path(self, path: str) -> str:
        """Resuelve `path` dentro de `base_path`, rechazando intentos de
        salir del directorio permitido (ej. "../../etc")."""
        if not path:
            path = "."
        joined = path if path.startswith("/") else posixpath.join(self.config.base_path, path)
        normalized = posixpath.normpath(joined)
        base = posixpath.normpath(self.config.base_path)
        if normalized != base and not normalized.startswith(base.rstrip("/") + "/"):
            raise SftpFtpSecurityError(
                f"Ruta no permitida: {path!r} resuelve fuera del directorio raíz "
                f"configurado ({self.config.base_path!r}). Esta protección evita "
                "que el agente acceda a archivos fuera del alcance previsto."
            )
        return normalized

    # ------------------------------------------------------------------ #
    # Conexión SFTP
    # ------------------------------------------------------------------ #

    def _open_sftp(self):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(
            _PinnedHostKeyPolicy(self.config.host_key_fingerprint, self._logger)
        )
        try:
            if self.config.auth_mode == "sftp_private_key":
                pkey = _load_private_key(self.config.private_key, self.config.private_key_passphrase)
                ssh.connect(
                    hostname=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    pkey=pkey,
                    timeout=self.config.timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
            else:
                ssh.connect(
                    hostname=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    password=self.config.password,
                    timeout=self.config.timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
        except paramiko.AuthenticationException as exc:
            raise SftpFtpAuthError(
                f"Autenticación SFTP fallida para {self.config.username}@{self.config.host}: {exc}"
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise SftpFtpNetworkError(
                f"Tiempo de espera agotado ({self.config.timeout}s) conectando a "
                f"{self.config.host}:{self.config.port}."
            ) from exc
        except (socket.gaierror, ConnectionRefusedError, OSError) as exc:
            if isinstance(exc, SftpFtpSecurityError):
                raise
            raise SftpFtpNetworkError(
                f"No se pudo conectar a {self.config.host}:{self.config.port}: {exc}"
            ) from exc
        return ssh, ssh.open_sftp()

    # ------------------------------------------------------------------ #
    # Conexión FTP/FTPS
    # ------------------------------------------------------------------ #

    def _open_ftp(self):
        ftp_cls = ftplib.FTP_TLS if self.config.use_tls else ftplib.FTP
        ftp = ftp_cls(timeout=self.config.timeout)
        try:
            ftp.connect(self.config.host, self.config.port, timeout=self.config.timeout)
            ftp.login(self.config.username, self.config.ftp_password)
            if self.config.use_tls:
                ftp.prot_p()  # cifra también el canal de datos, no solo el de comandos
        except ftplib.error_perm as exc:
            raise SftpFtpAuthError(
                f"Autenticación FTP fallida para {self.config.username}@{self.config.host}: {exc}"
            ) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise SftpFtpNetworkError(
                f"Tiempo de espera agotado ({self.config.timeout}s) conectando a "
                f"{self.config.host}:{self.config.port}."
            ) from exc
        except (socket.gaierror, ConnectionRefusedError, OSError) as exc:
            raise SftpFtpNetworkError(
                f"No se pudo conectar a {self.config.host}:{self.config.port}: {exc}"
            ) from exc
        return ftp

    # ------------------------------------------------------------------ #
    # Ping / prueba de conexión
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Verifica las credenciales conectando y listando el directorio raíz configurado."""
        self.list_directory(".")
        self._logger.info("Ping exitoso a %s (%s)", self.config.host, self.config.protocol)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar un directorio
    # ------------------------------------------------------------------ #

    def list_directory(self, path: str = ".") -> list[dict[str, Any]]:
        """Lista el contenido de un directorio remoto.

        Args:
            path: ruta del directorio, relativa a `base_path` o absoluta
                (siempre que quede dentro de `base_path`). Default: la
                raíz configurada.

        Returns:
            Lista de dicts con "name", "path", "size", "is_directory",
            "modified_time" (puede ser None en FTP si el servidor no lo reporta).

        Ejemplo:
            >>> client.list_directory("/reportes")
            [{'name': 'ventas.csv', 'path': '/reportes/ventas.csv', 'size': 2048, ...}]
        """
        resolved = self._resolve_path(path)

        if self.config.protocol == "sftp":
            ssh, sftp = self._open_sftp()
            try:
                entries = sftp.listdir_attr(resolved)
                result = [
                    {
                        "name": e.filename,
                        "path": posixpath.join(resolved, e.filename),
                        "size": e.st_size,
                        "is_directory": bool(e.st_mode and (e.st_mode & 0o040000)),
                        "modified_time": e.st_mtime,
                    }
                    for e in entries
                ]
            except FileNotFoundError as exc:
                raise SftpFtpDataError(f"Directorio no encontrado: {resolved!r}") from exc
            except PermissionError as exc:
                raise SftpFtpDataError(f"Sin permisos para listar {resolved!r}: {exc}") from exc
            finally:
                sftp.close()
                ssh.close()
        else:
            ftp = self._open_ftp()
            try:
                result = []
                try:
                    for name, facts in ftp.mlsd(resolved):
                        if name in (".", ".."):
                            continue
                        result.append({
                            "name": name,
                            "path": posixpath.join(resolved, name),
                            "size": int(facts.get("size", 0)) if facts.get("size") else None,
                            "is_directory": facts.get("type") == "dir",
                            "modified_time": facts.get("modify"),
                        })
                except ftplib.error_perm:
                    # El servidor no soporta MLSD; se usa NLST como respaldo
                    # (solo nombres, sin metadatos de tamaño/tipo/fecha).
                    names = ftp.nlst(resolved)
                    result = [
                        {
                            "name": posixpath.basename(n),
                            "path": n if n.startswith("/") else posixpath.join(resolved, n),
                            "size": None,
                            "is_directory": None,
                            "modified_time": None,
                        }
                        for n in names
                    ]
            except ftplib.error_perm as exc:
                raise SftpFtpDataError(f"No se pudo listar {resolved!r}: {exc}") from exc
            finally:
                ftp.quit()

        self._logger.info("list_directory %s: %d entrada(s)", resolved, len(result))
        return result

    # ------------------------------------------------------------------ #
    # Capacidad 2: subir un archivo
    # ------------------------------------------------------------------ #

    def upload_file(self, remote_path: str, content: bytes | str) -> dict[str, Any]:
        """Sube un archivo, a partir de contenido en memoria (bytes o texto).

        Args:
            remote_path: ruta destino remota, relativa a `base_path` o
                absoluta (dentro de `base_path`).
            content: contenido del archivo. Si es `str`, se codifica como UTF-8.

        Returns:
            Dict con "path" y "size" (bytes subidos).

        Ejemplo:
            >>> client.upload_file("/reportes/nuevo.csv", "col1,col2\\n1,2\\n")
            {'path': '/reportes/nuevo.csv', 'size': 14}
        """
        resolved = self._resolve_path(remote_path)
        data = content.encode("utf-8") if isinstance(content, str) else content

        if self.config.protocol == "sftp":
            ssh, sftp = self._open_sftp()
            try:
                with sftp.file(resolved, "wb") as f:
                    f.write(data)
            except (FileNotFoundError, PermissionError) as exc:
                raise SftpFtpDataError(f"No se pudo subir a {resolved!r}: {exc}") from exc
            finally:
                sftp.close()
                ssh.close()
        else:
            ftp = self._open_ftp()
            try:
                ftp.storbinary(f"STOR {resolved}", io.BytesIO(data))
            except ftplib.error_perm as exc:
                raise SftpFtpDataError(f"No se pudo subir a {resolved!r}: {exc}") from exc
            finally:
                ftp.quit()

        self._logger.info("Archivo subido: %s (%d bytes)", resolved, len(data))
        return {"path": resolved, "size": len(data)}

    # ------------------------------------------------------------------ #
    # Capacidad 3: descargar un archivo
    # ------------------------------------------------------------------ #

    def download_file(self, remote_path: str) -> bytes:
        """Descarga un archivo remoto y retorna su contenido en bytes.

        Args:
            remote_path: ruta del archivo remoto, relativa a `base_path`
                o absoluta (dentro de `base_path`).

        Returns:
            Contenido del archivo como `bytes`.

        Ejemplo:
            >>> contenido = client.download_file("/reportes/ventas.csv")
            >>> texto = contenido.decode("utf-8")
        """
        resolved = self._resolve_path(remote_path)

        if self.config.protocol == "sftp":
            ssh, sftp = self._open_sftp()
            try:
                with sftp.file(resolved, "rb") as f:
                    data = f.read()
            except FileNotFoundError as exc:
                raise SftpFtpDataError(f"Archivo no encontrado: {resolved!r}") from exc
            except PermissionError as exc:
                raise SftpFtpDataError(f"Sin permisos para leer {resolved!r}: {exc}") from exc
            finally:
                sftp.close()
                ssh.close()
        else:
            ftp = self._open_ftp()
            buffer = io.BytesIO()
            try:
                ftp.retrbinary(f"RETR {resolved}", buffer.write)
            except ftplib.error_perm as exc:
                raise SftpFtpDataError(f"No se pudo descargar {resolved!r}: {exc}") from exc
            finally:
                ftp.quit()
            data = buffer.getvalue()

        self._logger.info("Archivo descargado: %s (%d bytes)", resolved, len(data))
        return data

    # ------------------------------------------------------------------ #
    # Capacidad 4: mover/renombrar un archivo
    # ------------------------------------------------------------------ #

    def move_file(self, source_path: str, destination_path: str) -> dict[str, Any]:
        """Mueve (o renombra) un archivo remoto.

        Args:
            source_path: ruta actual del archivo.
            destination_path: ruta destino.

        Returns:
            Dict con "source" y "destination".

        Ejemplo:
            >>> client.move_file("/entrantes/pedido.csv", "/procesados/pedido.csv")
            {'source': '/entrantes/pedido.csv', 'destination': '/procesados/pedido.csv'}
        """
        resolved_src = self._resolve_path(source_path)
        resolved_dst = self._resolve_path(destination_path)

        if self.config.protocol == "sftp":
            ssh, sftp = self._open_sftp()
            try:
                sftp.rename(resolved_src, resolved_dst)
            except FileNotFoundError as exc:
                raise SftpFtpDataError(f"Archivo no encontrado: {resolved_src!r}") from exc
            except OSError as exc:
                raise SftpFtpDataError(
                    f"No se pudo mover {resolved_src!r} a {resolved_dst!r}: {exc}"
                ) from exc
            finally:
                sftp.close()
                ssh.close()
        else:
            ftp = self._open_ftp()
            try:
                ftp.rename(resolved_src, resolved_dst)
            except ftplib.error_perm as exc:
                raise SftpFtpDataError(
                    f"No se pudo mover {resolved_src!r} a {resolved_dst!r}: {exc}"
                ) from exc
            finally:
                ftp.quit()

        self._logger.info("Archivo movido: %s -> %s", resolved_src, resolved_dst)
        return {"source": resolved_src, "destination": resolved_dst}

    # ------------------------------------------------------------------ #
    # Capacidad 5: eliminar un archivo (SÍ soportado en este conector)
    # ------------------------------------------------------------------ #

    def delete_file(self, remote_path: str) -> dict[str, Any]:
        """Elimina un archivo remoto de forma permanente.

        ⚠️ A diferencia de la mayoría de conectores de Ruvic, esta
        operación SÍ se ejecuta de verdad — no está bloqueada. Úsala con
        cuidado; no hay papelera de reciclaje ni deshacer.

        Args:
            remote_path: ruta del archivo a eliminar.

        Returns:
            Dict con "path" y "deleted": True.

        Ejemplo:
            >>> client.delete_file("/temp/borrame.txt")
            {'path': '/temp/borrame.txt', 'deleted': True}
        """
        resolved = self._resolve_path(remote_path)

        if self.config.protocol == "sftp":
            ssh, sftp = self._open_sftp()
            try:
                sftp.remove(resolved)
            except FileNotFoundError as exc:
                raise SftpFtpDataError(f"Archivo no encontrado: {resolved!r}") from exc
            except PermissionError as exc:
                raise SftpFtpDataError(f"Sin permisos para eliminar {resolved!r}: {exc}") from exc
            finally:
                sftp.close()
                ssh.close()
        else:
            ftp = self._open_ftp()
            try:
                ftp.delete(resolved)
            except ftplib.error_perm as exc:
                raise SftpFtpDataError(f"No se pudo eliminar {resolved!r}: {exc}") from exc
            finally:
                ftp.quit()

        self._logger.info("Archivo eliminado: %s", resolved)
        return {"path": resolved, "deleted": True}
