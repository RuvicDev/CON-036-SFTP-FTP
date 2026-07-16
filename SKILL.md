---
name: sftp-ftp
description: "Usa la librería ruvic_sftp_ftp_connector para intercambiar archivos con un servidor remoto por SFTP o FTP/FTPS - listar el contenido de un directorio (list_directory), subir un archivo (upload_file), descargar un archivo (download_file), mover o renombrar un archivo (move_file), y eliminar un archivo (delete_file). Úsala cuando el usuario pida listar, subir, descargar, mover o eliminar archivos en un servidor SFTP/FTP. A diferencia de otros conectores de Ruvic, delete_file SÍ elimina archivos de forma real y permanente."
triggers:
- sftp
- ftp
- ftps
- subir archivo
- descargar archivo
- transferencia de archivos
---

# Conector SFTP/FTP (ruvic_sftp_ftp_connector)

Librería Python para listar, subir, descargar, mover y eliminar archivos en un servidor remoto por SFTP o FTP/FTPS. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/tu-org/conector-sftp-ftp.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `sftp_ftp` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_SFTP_FTP_HOST` / `..._USERNAME` | Siempre requeridas |
| `RUVIC_SFTP_FTP_PASSWORD` | Si el modo es SFTP con contraseña |
| `RUVIC_SFTP_FTP_PRIVATE_KEY` / `..._PRIVATE_KEY_PASSPHRASE` | Si el modo es SFTP con clave privada |
| `RUVIC_SFTP_FTP_FTP_PASSWORD` / `..._USE_TLS` | Si el modo es FTP/FTPS |
| `RUVIC_SFTP_FTP_HOST_KEY_FINGERPRINT` | (opcional, solo SFTP) verificación de identidad del servidor |
| `RUVIC_SFTP_FTP_BASE_PATH` | (opcional) directorio raíz permitido, default `/` |
| `RUVIC_SFTP_FTP_REQUEST_TIMEOUT` | (opcional) segundos, default `20` |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Conexión (siempre igual)

```python
from ruvic_sftp_ftp_connector import SftpFtpClient

client = SftpFtpClient()  # lee RUVIC_SFTP_FTP_* del entorno automáticamente
```

El código generado nunca necesita saber si el protocolo activo es SFTP o FTP — la interfaz es idéntica en ambos casos.

## Sobre las rutas — quedan encerradas en `base_path`

Todas las rutas que pases (relativas o absolutas) se resuelven **dentro** del directorio raíz configurado. Si intentas construir una ruta que "se sale" de ahí (ej. `"../../etc/passwd"`), el conector la rechaza automáticamente con `SftpFtpSecurityError` — no intentes rodear esta protección.

## Capacidad 1 — Listar un directorio

```python
entradas = client.list_directory("/reportes")
for e in entradas:
    tipo = "carpeta" if e["is_directory"] else "archivo"
    print(f"{e['name']} ({tipo}, {e['size']} bytes)")
```

## Capacidad 2 — Subir un archivo

El contenido se pasa **en memoria** (bytes o texto), no como una ruta de archivo local — genera el contenido primero y súbelo directamente:

```python
client.upload_file("/reportes/nuevo.csv", "col1,col2\n1,2\n")
# o con bytes:
client.upload_file("/reportes/imagen.png", datos_binarios)
```

## Capacidad 3 — Descargar un archivo

Retorna el contenido directamente (no lo guarda en un disco local, ya que el runtime del agente puede no tener acceso a disco persistente):

```python
contenido = client.download_file("/reportes/ventas.csv")
texto = contenido.decode("utf-8")  # si es un archivo de texto
```

## Capacidad 4 — Mover/renombrar un archivo

```python
client.move_file("/entrantes/pedido.csv", "/procesados/pedido.csv")
```

## Capacidad 5 — Eliminar un archivo ⚠️

```python
client.delete_file("/temp/borrame.txt")
```

**A diferencia de todos los demás conectores de Ruvic, esta operación SÍ se ejecuta de verdad.** No hay papelera de reciclaje ni deshacer. Antes de llamarla, confirma con el usuario que realmente quiere eliminar ese archivo específico — no lo asumas por una instrucción ambigua como "limpia esa carpeta".

## Manejo de errores

```python
from ruvic_sftp_ftp_connector import (
    SftpFtpAuthError, SftpFtpNetworkError, SftpFtpSecurityError, SftpFtpDataError,
)

try:
    client.list_directory("/reportes")
except SftpFtpAuthError:
    print("Credenciales inválidas — revisa la configuración del conector")
except SftpFtpNetworkError:
    print("No se pudo conectar al servidor — revisa la red")
except SftpFtpSecurityError as e:
    print(f"Bloqueado por seguridad: {e}")  # ruta fuera de base_path, o host key no coincide
except SftpFtpDataError as e:
    print(f"Error de datos: {e}")  # ej. archivo/directorio inexistente
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_SFTP_FTP_*` (el constructor de `SftpFtpClient` ya lo hace).
2. Nunca imprimas `RUVIC_SFTP_FTP_PASSWORD`, `..._PRIVATE_KEY`, ni `..._FTP_PASSWORD` en logs ni en la salida.
3. Antes de usar `delete_file()`, confirma la intención del usuario — es la única operación irreversible de este conector.
4. No intentes construir rutas que se salgan del directorio raíz configurado; es una protección de seguridad activa, no una limitación a evadir.
5. En FTP (no FTPS), algunos servidores no soportan `MLSD` (listado con metadatos) — en ese caso `list_directory` retorna entradas con `size`/`is_directory`/`modified_time` en `None`. No asumas que siempre vienen esos datos completos.
6. `upload_file`/`download_file` trabajan con contenido en memoria, no con rutas de archivo local del sistema donde corre el agente — genera o procesa el contenido en variables Python, no asumas acceso a disco.
