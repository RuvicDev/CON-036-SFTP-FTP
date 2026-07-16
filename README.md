# conector-sftp-ftp

Conector Ruvic para intercambio de archivos por **SFTP** (SSH) o **FTP/FTPS**, con protección de path traversal y verificación de identidad del servidor.

## Capacidades

`list_directory`, `upload_file`, `download_file`, `move_file`, `delete_file`. ⚠️ A diferencia de la mayoría de conectores de Ruvic, `delete_file` **sí elimina archivos de forma real y permanente** — es parte del alcance pedido para este conector, no un descuido.

## Protecciones de seguridad incorporadas

1. **Directorio raíz configurable (`base_path`)**: todas las rutas quedan encerradas dentro de esta carpeta. Un intento de ruta tipo `../../etc/passwd` se rechaza automáticamente (protección de path traversal).
2. **Verificación de host key SSH (solo SFTP)**: si configuras `host_key_fingerprint`, cada conexión valida que el servidor sea exactamente el esperado (previene ataques man-in-the-middle). Si no lo configuras, se acepta la clave en la primera conexión con una advertencia registrada (Trust On First Use) — igual que un cliente SSH interactivo la primera vez.
3. **FTPS por defecto**: el modo FTP viene con `use_tls=true` por defecto — FTP sin cifrar expone contraseñas y archivos en texto plano.

## Instalación

Requiere **Python ≥ 3.10**.

```bash
pip install git+https://github.com/tu-org/conector-sftp-ftp.git#subdirectory=lib
```

Para desarrollo local (editable, en un venv limpio):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib
```

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_SFTP_FTP_HOST` / `RUVIC_SFTP_FTP_USERNAME` | Sí | Siempre requeridas |
| `RUVIC_SFTP_FTP_PORT` | No | Default `22` (SFTP) o `21` (FTP) |
| `RUVIC_SFTP_FTP_PASSWORD` | Si modo SFTP con contraseña | Contraseña SSH |
| `RUVIC_SFTP_FTP_PRIVATE_KEY` / `RUVIC_SFTP_FTP_PRIVATE_KEY_PASSPHRASE` | Si modo SFTP con clave | Clave privada PEM/OpenSSH completa |
| `RUVIC_SFTP_FTP_FTP_PASSWORD` / `RUVIC_SFTP_FTP_USE_TLS` | Si modo FTP/FTPS | Contraseña FTP y si usar TLS (default `true`) |
| `RUVIC_SFTP_FTP_HOST_KEY_FINGERPRINT` | No (recomendado en SFTP) | Huella SHA256 esperada del servidor |
| `RUVIC_SFTP_FTP_BASE_PATH` | No | Directorio raíz permitido, default `/` |
| `RUVIC_SFTP_FTP_REQUEST_TIMEOUT` | No | Segundos, default `20` |

El modo se detecta automáticamente según qué variables estén presentes: `PRIVATE_KEY` → SFTP con clave; si no, `FTP_PASSWORD` → FTP/FTPS; si no, `PASSWORD` → SFTP con contraseña.

## Permisos / prerrequisitos en el servidor

- Un **usuario dedicado** a esta integración, idealmente con acceso **chroot/jail** al directorio que realmente necesita usar (muchos servidores SFTP/FTP lo soportan de forma nativa).
- Permisos de lectura sobre el directorio para `list_directory`/`download_file`.
- Permisos de escritura para `upload_file`/`move_file`.
- Permisos de eliminación explícitos si se va a usar `delete_file` — si no quieres permitir eliminación real, no otorgues ese permiso al usuario en el servidor (el conector no tiene un interruptor propio para bloquearlo, la restricción debe venir del lado del servidor).

## Cómo correr las pruebas locales

Puedes usar un contenedor Docker local de SFTP para pruebas sin depender de un servidor externo:

```bash
docker run -d -p 2222:22 -v /tmp/sftp-data:/home/pruebas/upload \
  atmoz/sftp pruebas:contraseña123:1001

export RUVIC_SFTP_FTP_HOST=localhost
export RUVIC_SFTP_FTP_PORT=2222
export RUVIC_SFTP_FTP_USERNAME=pruebas
export RUVIC_SFTP_FTP_PASSWORD=contraseña123
export RUVIC_SFTP_FTP_BASE_PATH=/upload

python test_connection.py
python validate_local.py
```

Prueba también el caso de error:

```bash
RUVIC_SFTP_FTP_PASSWORD=incorrecta python test_connection.py
# FALLO: Autenticación fallida: ...
```

## Limitaciones conocidas

- No implementa creación/eliminación de directorios (solo archivos).
- En FTP (no FTPS), si el servidor no soporta el comando `MLSD`, `list_directory` retorna solo nombres, sin tamaño/tipo/fecha (usa `NLST` como respaldo).
- Cada operación abre y cierra su propia conexión (no mantiene una sesión persistente) — más simple y robusto para uso esporádico desde un agente, pero implica una pequeña sobrecarga si se hacen muchas operaciones seguidas.
- No reintenta automáticamente ante fallos transitorios de red.

## Notas de integración

- El paquete pip es `ruvic-sftp-ftp-connector`; el import name es `ruvic_sftp_ftp_connector`.
- Dependencia externa: `paramiko` (SFTP). FTP/FTPS usa `ftplib` de la librería estándar de Python.
- Ver `SKILL.md` para los ejemplos de uso que consume el agente.
