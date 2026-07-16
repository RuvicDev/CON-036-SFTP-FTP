"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_SFTP_FTP_.

Soporta tres modos, detectados automáticamente por las variables presentes:
- "sftp_password": SFTP con usuario/contraseña (requiere PASSWORD).
- "sftp_private_key": SFTP con clave privada SSH (requiere PRIVATE_KEY).
- "ftp": FTP o FTPS clásico (requiere FTP_PASSWORD).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PREFIX = "RUVIC_SFTP_FTP_"


@dataclass(frozen=True)
class SftpFtpConfig:
    """Parámetros de conexión a un servidor SFTP o FTP/FTPS."""

    protocol: str  # "sftp" | "ftp"
    auth_mode: str  # "sftp_password" | "sftp_private_key" | "ftp"
    host: str
    port: int
    username: str
    password: str = ""
    private_key: str = ""
    private_key_passphrase: str = ""
    host_key_fingerprint: str = ""
    ftp_password: str = ""
    use_tls: bool = True
    base_path: str = "/"
    timeout: int = 20

    @classmethod
    def from_env(cls) -> "SftpFtpConfig":
        """Construye la configuración desde las variables RUVIC_SFTP_FTP_*.

        Detecta el modo automáticamente: PRIVATE_KEY presente -> SFTP con
        clave; si no, FTP_PASSWORD presente -> FTP/FTPS; si no, PASSWORD
        presente -> SFTP con contraseña.

        Raises:
            ValueError: si faltan HOST/USERNAME, o las credenciales del
                modo detectado.
        """
        host = os.environ.get(f"{ENV_PREFIX}HOST", "").strip()
        username = os.environ.get(f"{ENV_PREFIX}USERNAME", "").strip()
        if not host or not username:
            raise ValueError(
                f"Faltan variables de entorno del conector sftp_ftp: "
                f"{ENV_PREFIX}HOST y/o {ENV_PREFIX}USERNAME. "
                "Configura el conector en Settings → Conectores."
            )

        private_key = os.environ.get(f"{ENV_PREFIX}PRIVATE_KEY", "").strip()
        ftp_password = os.environ.get(f"{ENV_PREFIX}FTP_PASSWORD", "").strip()
        password = os.environ.get(f"{ENV_PREFIX}PASSWORD", "").strip()

        base_path = os.environ.get(f"{ENV_PREFIX}BASE_PATH", "/").strip() or "/"
        if not base_path.startswith("/"):
            base_path = "/" + base_path
        timeout = int(os.environ.get(f"{ENV_PREFIX}REQUEST_TIMEOUT", "20"))

        if private_key:
            port = int(os.environ.get(f"{ENV_PREFIX}PORT", "22"))
            return cls(
                protocol="sftp",
                auth_mode="sftp_private_key",
                host=host,
                port=port,
                username=username,
                private_key=private_key,
                private_key_passphrase=os.environ.get(f"{ENV_PREFIX}PRIVATE_KEY_PASSPHRASE", ""),
                host_key_fingerprint=os.environ.get(f"{ENV_PREFIX}HOST_KEY_FINGERPRINT", "").strip(),
                base_path=base_path,
                timeout=timeout,
            )

        if ftp_password:
            port = int(os.environ.get(f"{ENV_PREFIX}PORT", "21"))
            use_tls_raw = os.environ.get(f"{ENV_PREFIX}USE_TLS", "true").strip().lower()
            return cls(
                protocol="ftp",
                auth_mode="ftp",
                host=host,
                port=port,
                username=username,
                ftp_password=ftp_password,
                use_tls=use_tls_raw in ("true", "1", "yes"),
                base_path=base_path,
                timeout=timeout,
            )

        if password:
            port = int(os.environ.get(f"{ENV_PREFIX}PORT", "22"))
            return cls(
                protocol="sftp",
                auth_mode="sftp_password",
                host=host,
                port=port,
                username=username,
                password=password,
                host_key_fingerprint=os.environ.get(f"{ENV_PREFIX}HOST_KEY_FINGERPRINT", "").strip(),
                base_path=base_path,
                timeout=timeout,
            )

        raise ValueError(
            f"Falta una credencial válida del conector sftp_ftp: define "
            f"{ENV_PREFIX}PASSWORD (SFTP con contraseña), "
            f"{ENV_PREFIX}PRIVATE_KEY (SFTP con clave), o "
            f"{ENV_PREFIX}FTP_PASSWORD (FTP/FTPS)."
        )
