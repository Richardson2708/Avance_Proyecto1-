# Ejecutar el bot de KPIs NOC

## Visual Studio Code

Abre esta carpeta en Visual Studio Code. En la terminal de PowerShell ejecuta:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe bot_kpis.py
```

Si ya tienes el entorno y las dependencias, usa únicamente el último comando. Si py no está disponible, utiliza python en el primer comando. Se requiere Python 3.10 o posterior.

El bot busca Calculo_KPIs.csv junto al programa. Si no lo encuentra, puedes indicar el archivo completo o la carpeta que lo contiene.

## Google Colab

1. En https://colab.research.google.com/ selecciona Archivo → Subir notebook.
2. Abre Bot_KPIs_Colab.ipynb.
3. Ejecuta las tres secciones en orden: instalar NLTK, crear el programa e iniciar el bot.
4. Selecciona Calculo_KPIs.csv cuando se solicite y escribe tus preguntas.
5. Escribe adiós para terminar.

El notebook incluye el mismo programa comentado que la versión local. No necesitas subir bot_kpis.py. Los datos se cargan al entorno de tu cuenta de Colab.

## Ejemplos

- KPI TTT del 15 de octubre de 2026
- KPI TTC de lo que va de la semana
- KPI TTN de las 10 a 11 am del 18 de octubre de 2026
- Estatus del folio 261013-001

Otros comandos: ayuda, datos, detalle, exportar y cargar archivo.

Las fechas sin año usan el año actual; sin periodo se consulta el mes actual hasta ahora. El CSV suministrado contiene aperturas del 13 al 23 de octubre de 2026.

