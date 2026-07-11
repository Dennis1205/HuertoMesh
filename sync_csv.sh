#!/bin/bash
cd /home/pi/HuertoMesh_clean

# Traer cambios remotos y aplicar encima de los locales
git pull origin main --rebase

# Copiar el CSV actualizado desde DATALOGGER
cp /home/pi/DATALOGGER/datos_tesis_v5_metricas_completas.csv .

# Validar que el CSV tenga siempre el mismo número de columnas (ejemplo: 23)
EXPECTED_COLS=23
ACTUAL_COLS=$(head -n 1 datos_tesis_v5_metricas_completas.csv | awk -F',' '{print NF}')

if [ "$ACTUAL_COLS" -eq "$EXPECTED_COLS" ]; then
    # Añadir el CSV actualizado
    git add datos_tesis_v5_metricas_completas.csv

    # Commit automático con fecha
    git commit -m "Actualización automática de CSV $(date)" || echo "No hay cambios nuevos"

    # Push al remoto
    git push origin main >> sync.log 2>&1
else
    echo "CSV corrupto: columnas esperadas $EXPECTED_COLS, encontradas $ACTUAL_COLS. No se sube."
fi

# Limpiar el log si supera 5 MB para no llenar memoria
LOGFILE="sync.log"
MAXSIZE=$((5*1024*1024)) # 5 MB
if [ -f "$LOGFILE" ]; then
    FILESIZE=$(stat -c%s "$LOGFILE")
    if [ "$FILESIZE" -gt "$MAXSIZE" ]; then
        echo "Log demasiado grande, se reinicia." > "$LOGFILE"
    fi
fi
