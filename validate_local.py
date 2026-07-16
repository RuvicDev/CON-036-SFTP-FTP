"""Validación local del conector sftp_ftp: ejercita las 5 capacidades.

Requiere las env vars RUVIC_SFTP_FTP_* exportadas contra un servidor de
prueba (puedes usar un contenedor Docker local de SFTP, ej. la imagen
"atmoz/sftp", o una cuenta FTP/FTPS de pruebas). No lo corras contra un
servidor productivo.
"""

from ruvic_sftp_ftp_connector import SftpFtpClient, setup_logging

setup_logging("INFO")
client = SftpFtpClient()

print("== 1. Listar el directorio raíz ==")
entradas = client.list_directory(".")
print(f"  {len(entradas)} entrada(s) encontrada(s)")
for e in entradas[:5]:
    print(f"    {e}")

print("== 2. Subir un archivo de prueba ==")
subida = client.upload_file("ruvic_prueba.txt", "Archivo de prueba creado por validate_local.py\n")
print(f"  {subida}")

print("== 3. Descargar el archivo recién subido ==")
contenido = client.download_file("ruvic_prueba.txt")
print(f"  Contenido leído: {contenido!r}")
assert b"prueba" in contenido, "El contenido descargado no coincide con lo subido"

print("== 4. Mover el archivo a un nuevo nombre ==")
movido = client.move_file("ruvic_prueba.txt", "ruvic_prueba_movido.txt")
print(f"  {movido}")

print("== 5. Confirmar que la ruta fuera de base_path se bloquea ==")
try:
    client.list_directory("../../etc")
    print("  ERROR: debió bloquearse y no lo hizo")
except Exception as exc:
    print(f"  OK, bloqueado correctamente: {exc}")

print("== 6. Eliminar el archivo de prueba (limpieza) ==")
eliminado = client.delete_file("ruvic_prueba_movido.txt")
print(f"  {eliminado}")

print("\nTodas las capacidades ejercitadas correctamente.")
