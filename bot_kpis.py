"""Bot de KPIs NOC basado en reglas. Python 3.10+ y NLTK.

Las respuestas normales muestran solo periodo y resultados por severidad.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from nltk.tokenize import wordpunct_tokenize
except ImportError:
    wordpunct_tokenize = None

ARCHIVO = "Calculo_KPIs.csv"
COLUMNAS = "CODIGO_FOLIO DESC_FOLIO DESC_ORIGEN_FOLIO_NORM DESC_PRIORIDAD TIPO DESC_GRUPO_TRABAJO REGION FECHA_APERTURA FECHA_INICIO_FALLA TIEMPO_VIDA TIEMPO_APERTURA MINUTOS_AP SEMANA STATUS_REAL STATUS_REV OBSERVACIONES ANO MES DIAT TBCKL DESC_ESTADO DESC_SUBESTADO FECHA_INICIO_TTC FECHA_HORA_CIERRE HORA_CIERRE ORIGEN_FECHA_CIERRE ORIGEN_INICIO_TTC TTC_MINUTOS TTC VALIDACION_TTC TTN RED_SEV TTR SOLICITA_NOMBRE_CIERRE MOD_CIERRE RN".split()
ORIGENES = {"rose", "gestion de eventos", "ccr mexico transmision", "ccr mexico plataformas", "ccr mexico datos", "ccr mexico acceso"}
MESES = dict(zip("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), range(1, 13)))
MESES["setiembre"] = 9
SIN_FOLIOS = "No se cuentan con folios de esta severidad para realizar el cálculo"
FORMATOS = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")


def normalizar(texto):
    """Quita diferencias de acentos, espacios y mayúsculas para comparar textos."""
    limpio = "".join(c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c))
    return " ".join(limpio.casefold().split())


def ahora_mexico():
    """Obtiene la hora de Ciudad de México, sin depender de la zona del equipo."""
    return datetime.now(timezone(timedelta(hours=-6))).replace(tzinfo=None)


def fecha(valor):
    """Interpreta formatos de fecha conocidos; devuelve None si el dato es inválido."""
    for formato in FORMATOS:
        try:
            return datetime.strptime(str(valor or "").strip(), formato)
        except ValueError:
            pass
    return None


def resolver_ruta_csv(ruta=None):
    """Acepta una ruta de archivo o busca Calculo_KPIs.csv dentro de una carpeta."""
    valor = str(ruta).strip().strip("\"'") if ruta is not None else str(Path(__file__).resolve().parent / ARCHIVO)
    destino = Path(valor).expanduser()
    return destino / ARCHIVO if destino.is_dir() else destino


def valida_archivo(ruta=None):
    """Comprueba si el CSV existe junto al programa o en la ruta indicada."""
    return resolver_ruta_csv(ruta).is_file()


def leer_csv(ruta):
    """Lee el CSV y comprueba encabezados, número de campos y folios únicos."""
    ruta = resolver_ruta_csv(ruta)
    if not ruta.is_file():
        raise ValueError(f"No se encontró el archivo CSV: {ruta}. Indica el archivo completo o la carpeta que contiene {ARCHIVO}.")
    if ruta.suffix.lower() != ".csv":
        raise ValueError("Se requiere un archivo .csv; no selecciones un libro .xlsx.")
    datos = ruta.read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252")
    try:
        separador = csv.Sniffer().sniff(texto[:65536], delimiters=",;\t").delimiter
    except csv.Error:
        separador = ","
    lector = csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador)
    encabezados = [c.strip().upper() for c in lector.fieldnames or []]
    if len(encabezados) != len(set(encabezados)):
        raise ValueError("El CSV contiene columnas duplicadas.")
    if set(encabezados) != set(COLUMNAS):
        raise ValueError(f"Estructura incorrecta. Faltan: {sorted(set(COLUMNAS)-set(encabezados))}. Sobran: {sorted(set(encabezados)-set(COLUMNAS))}.")
    filas, vistos = [], set()
    for numero, r in enumerate(lector, 2):
        if None in r or any(v is None for v in r.values()):
            raise ValueError(f"La fila lógica {numero} no tiene 36 campos.")
        r = {k.strip().upper(): v.strip() for k, v in r.items()}
        codigo = r["CODIGO_FOLIO"]
        if not re.fullmatch(r"\d{6}-\d{3,}", codigo) or fecha("20" + codigo[:2] + "-" + codigo[2:4] + "-" + codigo[4:6]) is None:
            raise ValueError(f"Folio inválido en la fila {numero}: {codigo!r}.")
        if codigo in vistos:
            raise ValueError(f"Folio duplicado: {codigo}. Consolida la base antes de calcular.")
        vistos.add(codigo)
        filas.append(r)
    if not filas:
        raise ValueError("El CSV no contiene registros.")
    return filas


def valida_estructura(ruta):
    """Indica si el archivo tiene la estructura requerida y explica los errores."""
    try:
        filas = leer_csv(ruta)
        return True, f"Archivo válido: {len(filas):,} registros y 36 columnas."
    except PermissionError:
        return False, "No se pudo leer el archivo por permisos. Comprueba que sea un CSV accesible y que tengas permiso de lectura."
    except (ValueError, OSError, csv.Error, UnicodeError) as e:
        return False, str(e)


def carga_archivo(destino=None, colab=False, entrada=input):
    """Solicita un CSV y lo activa únicamente después de validarlo."""
    destino = resolver_ruta_csv(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    while True:
        if colab:
            from google.colab import files
            print("Selecciona un solo CSV o cancela la selección.")
            cargados = files.upload(target_dir=str(destino.parent / "cargas"))
            if not cargados:
                return None
            if len(cargados) != 1:
                print("Selecciona solo un archivo CSV.")
                continue
            nombre, datos = next(iter(cargados.items()))
            if Path(nombre).suffix.lower() != ".csv":
                print("Se requiere un CSV, no un archivo XLSX.")
                continue
            origen = destino.with_suffix(".validacion.csv")
            origen.write_bytes(datos)
        else:
            respuesta = entrada("Ruta completa del CSV o carpeta que lo contiene (o cancelar): ").strip().strip("\"'")
            if normalizar(respuesta) in {"", "cancelar", "salir"}:
                return None
            origen = resolver_ruta_csv(respuesta)
        correcto, mensaje = valida_estructura(origen)
        print(mensaje)
        if not correcto:
            continue
        if origen.resolve() != destino.resolve():
            try:
                shutil.copyfile(origen, destino)
            except OSError as e:
                print(f"El CSV es válido, pero no se pudo copiar a {destino}: {e}. Revisa los permisos de esa carpeta o cancela y usa --archivo con la ruta del CSV.")
                continue
        if colab and origen != destino:
            origen.unlink(missing_ok=True)
        return destino


def Intrucciones_bot():
    """Presenta una explicación breve del bot y ejemplos de consultas."""
    return ("BOT DE KPIs NOC — TTT, TTC y TTN\n"
            "Consulta por hora, día, semana o mes el estatus de los KPIs principales.\n"
            "Ejemplos: ¿Cuál es el KPI TTT del 15 de octubre de 2026?\n"
            "¿Cuál es el estatus del folio 261013-001?\n"
            "Puedes filtrar por tipo manual/automático y severidad SF1–SF4.\n"
            "Otros comandos: ayuda, datos, detalle, exportar y cargar archivo.\n"
            "Para terminar: adiós, bye, hasta luego, cya, ciao o salir.")


def saludo_inicial():
    """Da la bienvenida e invita a realizar una consulta."""
    return "¡Hola! Soy tu asistente de KPIs del NOC. ¿Qué deseas consultar?"


def despedida_bot():
    """Devuelve el mensaje de cierre de la conversación."""
    return "Hasta luego. Gracias por consultar los KPIs del NOC."


@dataclass
class Medicion:
    """Guarda el resultado de evaluar un folio, sin modificar sus datos originales."""
    fila: dict
    estado: str
    minutos: float | None = None
    motivo: str = ""
    discrepancia: bool = False


def severidad(fila):
    """Extrae SF1, SF2, SF3 o SF4 de la prioridad del folio."""
    m = re.search(r"\bSF[1-4]\b", fila.get("DESC_PRIORIDAD", ""), re.I)
    return m.group().upper() if m else "Sin severidad"


def calcular_ttt(fila):
    """Evalúa el tiempo entre la alarma y la creación del ticket según severidad."""
    sev = severidad(fila)
    if sev == "Sin severidad":
        return Medicion(fila, "Sin datos", motivo="Severidad no reconocida")
    inicio, fin = fecha(fila.get("FECHA_INICIO_FALLA")), fecha(fila.get("FECHA_APERTURA"))
    if inicio is None or fin is None:
        return Medicion(fila, "Sin datos", motivo="Fecha de alarma o apertura ausente/inválida")
    # Apertura menos alarma: la resta impresa en el Word está invertida.
    minutos = (fin - inicio).total_seconds() / 60
    if minutos < 0:
        return Medicion(fila, "Fecha inconsistente", minutos, "La apertura es anterior a la alarma")
    limite = 10 if sev in {"SF1", "SF2"} else 30
    return Medicion(fila, "En tiempo" if minutos <= limite else "Fuera de tiempo", minutos)


def calcular_ttc(fila):
    """Evalúa el cierre en hasta 20 minutos, solo para los estados permitidos."""
    if normalizar(fila.get("DESC_ESTADO", "")) not in {"folio cerrado", "solicitud cierre"}:
        return Medicion(fila, "No aplica", motivo="Estado no elegible para TTC")
    referencia = normalizar(fila.get("TTC", ""))
    if referencia == "no aplica":
        return Medicion(fila, "No aplica", motivo="TTC indica No aplica")
    inicio, fin = fecha(fila.get("FECHA_INICIO_TTC")), fecha(fila.get("FECHA_HORA_CIERRE"))
    if inicio is None or fin is None:
        return Medicion(fila, "Sin datos", motivo="Inicio TTC o cierre ausente/inválido")
    minutos = (fin - inicio).total_seconds() / 60
    if minutos < 0:
        return Medicion(fila, "Fecha inconsistente", minutos, "El cierre es anterior al inicio TTC")
    cumple = minutos <= 20
    esperado = "dentro sla" if cumple else "fuera de sla"
    return Medicion(fila, "En tiempo" if cumple else "Fuera de tiempo", minutos,
                    discrepancia=referencia != esperado)


def calcular_ttn(fila):
    """Usa la columna TTN: solo Dentro de SLA cuenta como cumplimiento."""
    cumple = normalizar(fila.get("TTN", "")) == "dentro de sla"
    return Medicion(fila, "En tiempo" if cumple else "Fuera de tiempo", motivo="Etiqueta de TTN; fase 1")


CALCULOS = {"TTT": calcular_ttt, "TTC": calcular_ttc, "TTN": calcular_ttn}


def resumen_mediciones(mediciones):
    """Cuenta resultados y calcula el porcentaje sin redondear antes de evaluar la meta."""
    estados = Counter(m.estado for m in mediciones)
    dentro, fuera = estados["En tiempo"], estados["Fuera de tiempo"]
    total = dentro + fuera
    return {"dentro": dentro, "fuera": fuera, "evaluables": total,
            "sin_datos": estados["Sin datos"], "inconsistentes": estados["Fecha inconsistente"],
            "no_aplica": estados["No aplica"], "porcentaje": 100 * dentro / total if total else None,
            "cumple": dentro * 100 >= total * 95 if total else None,
            "discrepancias": sum(m.discrepancia for m in mediciones)}


def grupo_trabajo(mediciones):
    """Ordena los grupos por folios fuera de tiempo cuando se pide ese detalle."""
    grupos = {m.fila["DESC_GRUPO_TRABAJO"] or "Sin grupo" for m in mediciones}
    resumen = [(g, resumen_mediciones([m for m in mediciones if (m.fila["DESC_GRUPO_TRABAJO"] or "Sin grupo") == g])) for g in grupos]
    return sorted(resumen, key=lambda item: (-item[1]["fuera"], item[0]))


def estatus_folio(filas, codigo):
    """Devuelve únicamente DESC_ESTADO, como solicita el Word actualizado."""
    if not re.fullmatch(r"\d{6}-\d{3,}", codigo):
        return "Indica un folio válido; por ejemplo, 261013-001."
    encontrados = [r for r in filas if r["CODIGO_FOLIO"] == codigo]
    if not encontrados:
        return "No encontré ese folio. Verifica el número y reformula la consulta o carga una base actualizada."
    return encontrados[0]["DESC_ESTADO"] or "No hay estado disponible para ese folio."


def identificar_intencion(texto):
    """Reconoce la consulta y extrae KPI, tipo de folio, severidad o número de ticket."""
    if wordpunct_tokenize is None:
        raise RuntimeError("Instala NLTK: python -m pip install -r requirements.txt")
    t = normalizar(texto)
    tokens = set(wordpunct_tokenize(t))
    if re.fullmatch(r"(?:adios|bye|hasta luego|cya|ciao|salir|terminar)[.!\s]*", t):
        return {"accion": "despedida"}
    for opciones, accion in [({"ayuda", "instrucciones", "menu", "ejemplos"}, "ayuda"),
                             ({"hola", "buenos dias", "buenas tardes"}, "saludo"),
                             ({"datos", "cobertura", "diagnostico"}, "datos")]:
        if t in opciones:
            return {"accion": accion}
    if tokens & {"cargar", "recargar"}:
        return {"accion": "cargar"}
    if "exportar" in tokens:
        return {"accion": "exportar"}
    folio = re.search(r"\b\d{6}-\d{3,}\b", t)
    if folio or tokens & {"estatus", "estado"} and tokens & {"folio", "ticket", "fg"}:
        return {"accion": "estatus", "folio": folio.group() if folio else None}
    kpis = [k for k in CALCULOS if k.lower() in tokens]
    for expresion, kpi in {"time to ticket": "TTT", "time to close": "TTC", "time to notify": "TTN"}.items():
        if expresion in t and kpi not in kpis:
            kpis.append(kpi)
    if "los tres" in t or tokens & {"todos"} and tokens & {"kpis", "indicadores"}:
        kpis = list(CALCULOS)
    automatico = bool(tokens & {"automatico", "automaticos", "automatica", "automaticas"})
    manual = bool(tokens & {"manual", "manuales"})
    tipo = "Automatico" if automatico and not manual else "Manual" if manual and not automatico else None
    sev = re.search(r"\bsf\s*([1-4])\b", t)
    relevante = bool(kpis or tokens & {"kpi", "kpis", "sla", "ans", "cumplimiento", "detalle", "detalles", "grupo", "grupos"})
    accion = "grupos" if tokens & {"grupo", "grupos"} else "detalle" if tokens & {"detalle", "detalles", "listado"} else "kpi"
    return {"accion": accion if relevante else "desconocida",
            "kpis": kpis, "tipo": tipo, "severidad": "SF" + sev.group(1) if sev else None}


@dataclass
class Periodo:
    """Representa un intervalo: inicio incluido y fin excluido."""
    inicio: datetime
    fin: datetime
    descripcion: str


def periodo_consulta(texto, ahora=None):
    """Convierte las fechas de la pregunta en un intervalo de consulta."""
    ahora = ahora or ahora_mexico()
    t = normalizar(texto)
    dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    barra = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", t)
    nombre = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")(?:\s+(?:de\s+)?(20\d{2}))?\b", t)
    try:
        if iso:
            inicio = datetime(*map(int, iso.groups()))
        elif barra:
            d, m, a = map(int, barra.groups())
            inicio = datetime(a + 2000 if a < 100 else a, m, d)
        elif nombre:
            d, m, a = nombre.groups()
            inicio = datetime(int(a or ahora.year), MESES[m], int(d))
        else:
            inicio = None
        if inicio:
            fin, etiqueta = inicio + timedelta(days=1), "Día solicitado"
        elif "ayer" in t:
            inicio, fin, etiqueta = dia - timedelta(days=1), dia, "Ayer"
        elif "semana pasada" in t:
            fin = dia - timedelta(days=dia.weekday())
            inicio, etiqueta = fin - timedelta(days=7), "Semana pasada"
        elif "semana" in t:
            inicio, fin, etiqueta = dia - timedelta(days=dia.weekday()), ahora + timedelta(microseconds=1), "Semana actual hasta ahora"
        elif "mes pasado" in t:
            fin = dia.replace(day=1)
            inicio, etiqueta = (fin - timedelta(days=1)).replace(day=1), "Mes pasado"
        elif re.search(r"\bhoy\b|\bdia\b", t):
            inicio, fin, etiqueta = dia, ahora + timedelta(microseconds=1), "Día actual hasta ahora"
        else:
            mes = re.search(r"\b(" + "|".join(MESES) + r")(?:\s+(?:de\s+)?(20\d{2}))?\b", t)
            if mes:
                m, a = MESES[mes.group(1)], int(mes.group(2) or ahora.year)
                inicio, fin = datetime(a, m, 1), datetime(a + (m == 12), 1 if m == 12 else m + 1, 1)
                etiqueta = "Mes solicitado"
            else:
                inicio, fin, etiqueta = dia.replace(day=1), ahora + timedelta(microseconds=1), "Mes actual hasta ahora"
        if "semana" in t and (iso or barra or nombre):
            inicio -= timedelta(days=inicio.weekday())
            fin, etiqueta = inicio + timedelta(days=7), "Semana de la fecha indicada"
        hora = re.search(r"(?:de\s+(?:las\s+)?|entre\s+)(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:a|y|hasta|al)\s*(?:las\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
        if hora:
            h1, n1, p1, h2, n2, p2 = hora.groups()
            h1, n1 = convertir_hora(h1, n1, p1 or p2)
            h2, n2 = convertir_hora(h2, n2, p2 or p1)
            base = inicio.replace(hour=0, minute=0, second=0, microsecond=0) if (iso or barra or nombre or "ayer" in t) else dia
            inicio, fin = base.replace(hour=h1, minute=n1), base.replace(hour=h2, minute=n2)
            if fin <= inicio:
                raise ValueError("usa un intervalo ascendente dentro del mismo día")
            etiqueta = "Horario solicitado"
        elif "ultima hora" in t:
            inicio, fin, etiqueta = ahora - timedelta(hours=1), ahora + timedelta(microseconds=1), "Última hora"
        elif re.search(r"\b(hora|horas|am|pm)\b|\b\d{1,2}:\d{2}\b", t):
            raise ValueError("indica un intervalo, por ejemplo de las 10 a 11 am del 18 de octubre")
        if re.search(r"\b\d{1,2}/\d{1,2}\b", t) and not barra:
            raise ValueError("incluye el año en formato DD/MM/AAAA")
        if "entre el" in t or re.search(r"\bdel\s+\d+\s+al\s+\d+", t):
            raise ValueError("consulta un día, semana o mes a la vez")
        if re.search(r"\b(dia|del)\s+\d{1,2}\b", t) and not (nombre or barra or iso):
            raise ValueError("indica la fecha completa, por ejemplo 15 de octubre de 2026")
        return Periodo(inicio, fin, etiqueta)
    except ValueError as e:
        raise ValueError(f"No pude interpretar el periodo: {e}. Reformula la consulta.") from e


def convertir_hora(hora, minuto=None, am_pm=None):
    """Valida una hora y la convierte al formato de 24 horas."""
    h, m = int(hora), int(minuto or 0)
    if am_pm:
        if not 1 <= h <= 12:
            raise ValueError("la hora am/pm debe estar entre 1 y 12")
        h = h % 12 + (12 if am_pm == "pm" else 0)
    if not 0 <= h <= 23 or not 0 <= m <= 59:
        raise ValueError("hora inválida")
    return h, m


def describir_periodo(periodo):
    """Escribe el periodo en un formato corto y fácil de leer."""
    fin = periodo.fin
    if fin.microsecond:
        fin -= timedelta(microseconds=1)
    elif fin.time() == datetime.min.time() and periodo.inicio.time() == datetime.min.time():
        # Un día completo se presenta como fecha, sin confundir el límite exclusivo.
        ultimo = fin - timedelta(days=1)
        if ultimo.date() == periodo.inicio.date():
            return f"Periodo: {periodo.inicio:%d/%m/%Y} (día completo)"
        return f"Periodo: del {periodo.inicio:%d/%m/%Y} al {ultimo:%d/%m/%Y} (días completos)"
    return f"Periodo: del {periodo.inicio:%d/%m/%Y %H:%M} al {fin:%d/%m/%Y %H:%M}"


class BotKPIs:
    """Organiza los datos, interpreta consultas y prepara respuestas breves."""

    def __init__(self, ruta=None, reloj=None, campo_periodo="FECHA_APERTURA"):
        """Carga la base y conserva únicamente los orígenes NOC para los cálculos."""
        self.ruta = resolver_ruta_csv(ruta)
        self.filas = leer_csv(self.ruta)
        self.noc = [r for r in self.filas if normalizar(r["DESC_ORIGEN_FOLIO_NORM"]) in ORIGENES]
        self.reloj = reloj or ahora_mexico
        if campo_periodo not in {"FECHA_APERTURA", "FECHA_HORA_CIERRE"}:
            raise ValueError("Campo de periodo no admitido")
        self.campo_periodo = campo_periodo
        self.pendiente = None
        self.ultima = None
        self.historial = []
        self.terminado = False

    def datos(self):
        """Muestra la cobertura de la base cuando el usuario pide información de los datos."""
        fechas = [f for r in self.noc if (f := fecha(r["FECHA_APERTURA"]))]
        rango = f"{min(fechas):%d/%m/%Y %H:%M} a {max(fechas):%d/%m/%Y %H:%M}" if fechas else "Sin fechas válidas"
        return (f"Registros: {len(self.filas):,} | Alcance NOC: {len(self.noc):,}\n"
                f"Cobertura de aperturas: {rango}\n"
                "Los periodos relativos usan la fecha actual de Ciudad de México. El CSV no es una consulta en tiempo real.")

    def medir(self, kpi, periodo, tipo=None, sev=None):
        """Filtra los folios por periodo, tipo y severidad, y aplica el cálculo solicitado."""
        campo = self.campo_periodo if kpi == "TTC" else "FECHA_APERTURA"
        alcance = [r for r in self.noc if (not tipo or normalizar(r["TIPO"]) == normalizar(tipo)) and (not sev or severidad(r) == sev)]
        sin_fecha = sum(fecha(r[campo]) is None for r in alcance)
        seleccion = [r for r in alcance if (f := fecha(r[campo])) and periodo.inicio <= f < periodo.fin]
        return [CALCULOS[kpi](r) for r in seleccion], sin_fecha, campo

    def linea_severidad(self, nombre, mediciones):
        """Prepara el porcentaje y estado de una severidad, sin mostrar tablas extensas."""
        r = resumen_mediciones(mediciones)
        errores = r["sin_datos"] + r["inconsistentes"]
        if not r["evaluables"]:
            if errores:
                return f"{nombre}: Sin datos suficientes para calcular; {errores} folio(s) requieren revisión."
            return f"{nombre}: {SIN_FOLIOS}"
        estado = "Cumple" if r["cumple"] else "No cumple"
        parcial = f" (parcial: {errores} no evaluables)" if errores else ""
        return f"{nombre}: {r['porcentaje']:.2f}% - {estado}{parcial}"

    def consultar(self, consulta, texto):
        """Responde con periodo y resultado por severidad para TTT, TTC o TTN."""
        periodo = periodo_consulta(texto, self.reloj())
        salida = [describir_periodo(periodo)]
        if consulta.get("tipo"):
            salida.append("Tipo: " + consulta["tipo"])
        registros_auditoria = []
        hay_folios = False
        for kpi in consulta["kpis"]:
            ms, sin_fecha, campo = self.medir(kpi, periodo, consulta.get("tipo"), consulta.get("severidad"))
            registros_auditoria.extend((kpi, m) for m in ms)
            hay_folios |= bool(ms)
            salida.append(kpi)
            for sev in ([consulta["severidad"]] if consulta.get("severidad") else ["SF1", "SF2", "SF3", "SF4"]):
                salida.append(self.linea_severidad(sev, [m for m in ms if severidad(m.fila) == sev]))
            desconocidos = sum(severidad(m.fila) == "Sin severidad" for m in ms)
            if desconocidos:
                salida.append(f"Nota: {desconocidos} folio(s) sin severidad reconocida, fuera del desglose SF1–SF4.")
            if sin_fecha:
                salida.append(f"Nota: {sin_fecha} folio(s) del alcance sin fecha de periodo válida; requieren revisión.")
            if campo != "FECHA_APERTURA":
                salida.append("Periodo por fecha de cierre.")
            if consulta["accion"] == "detalle":
                salida.append("Folio | Severidad | Resultado | Minutos")
                for m in ms[:50]:
                    minutos = "N/A" if m.minutos is None else f"{m.minutos:.2f}"
                    salida.append(f"{m.fila['CODIGO_FOLIO']} | {severidad(m.fila)} | {m.estado} | {minutos}")
                if len(ms) > 50:
                    salida.append("Se muestran 50 filas. Usa exportar para obtener todo el detalle.")
            elif consulta["accion"] == "grupos":
                ranking = grupo_trabajo(ms)
                maximo = ranking[0][1]["fuera"] if ranking else 0
                if maximo:
                    nombres = [g for g, r in ranking if r["fuera"] == maximo]
                    salida.append(f"Mayor cantidad fuera de tiempo: {', '.join(nombres)} ({maximo} folios por grupo).")
                else:
                    salida.append("No hay folios evaluables fuera de tiempo para ordenar grupos.")
        if not hay_folios:
            salida.append("No hay información para ese periodo y filtros. Verifica las fechas y reformula la consulta o carga una base actualizada.")
        self.ultima = {"mediciones": registros_auditoria, "consulta": consulta, "periodo": periodo}
        return "\n".join(salida)

    def exportar(self):
        """Guarda el detalle de la última consulta en un CSV para revisión."""
        if not self.ultima:
            return "Primero realiza una consulta de KPI."
        carpeta = self.ruta.parent / "resultados"
        carpeta.mkdir(exist_ok=True)
        ruta = carpeta / ("detalle_kpis_" + self.reloj().strftime("%Y%m%d_%H%M%S_%f") + ".csv")
        campos = ["KPI", "CODIGO_FOLIO", "DESC_PRIORIDAD", "TIPO", "DESC_GRUPO_TRABAJO", "RESULTADO", "MINUTOS", "MOTIVO", "DISCREPANCIA_TTC", "FECHA_APERTURA", "FECHA_INICIO_FALLA", "FECHA_INICIO_TTC", "FECHA_HORA_CIERRE", "TTC", "TTN"]
        with ruta.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            for kpi, m in self.ultima["mediciones"]:
                r = {k: m.fila.get(k, "") for k in campos}
                r.update(KPI=kpi, RESULTADO=m.estado, MINUTOS=m.minutos, MOTIVO=m.motivo, DISCREPANCIA_TTC=m.discrepancia)
                # Evita que un texto se interprete como fórmula al abrirlo en Excel.
                w.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in r.items()})
        return f"Detalle exportado: {ruta}"

    def responder(self, texto):
        """Atiende una pregunta o solicita el dato que falta para poder responder."""
        try:
            c = identificar_intencion(texto)
            if self.pendiente:
                anterior = self.pendiente
                if anterior["accion"] != "estatus" and c.get("kpis"):
                    texto = anterior["texto"] + " " + texto
                    c = identificar_intencion(texto)
                self.pendiente = None
            accion = c["accion"]
            if accion == "despedida":
                self.terminado = True
                respuesta = despedida_bot()
            elif accion == "ayuda":
                respuesta = Intrucciones_bot()
            elif accion == "saludo":
                respuesta = saludo_inicial()
            elif accion == "datos":
                respuesta = self.datos()
            elif accion == "estatus":
                if c.get("folio"):
                    respuesta = estatus_folio(self.filas, c["folio"])
                else:
                    self.pendiente = c
                    respuesta = "¿Qué folio deseas consultar? Ejemplo: 261013-001."
            elif accion == "exportar":
                respuesta = self.exportar()
            elif accion == "cargar":
                respuesta = "Usa la opción de carga del programa para seleccionar el nuevo CSV."
            elif accion in {"kpi", "detalle", "grupos"}:
                if not c["kpis"]:
                    self.pendiente = {**c, "texto": texto}
                    respuesta = "¿Qué indicador deseas consultar: TTT, TTC o TTN?"
                else:
                    respuesta = self.consultar(c, texto)
            else:
                respuesta = "No pude identificar la consulta. Reformúlala; por ejemplo: KPI TTT del 15 de octubre de 2026."
        except (ValueError, OSError) as e:
            respuesta = str(e)
        self.historial.append({"usuario": texto, "bot": respuesta})
        return respuesta


def ejecutar(ruta=None, colab=False):
    """Inicia el bot y mantiene la conversación hasta que el usuario se despide."""
    if wordpunct_tokenize is None:
        print("Instala NLTK: python -m pip install -r requirements.txt")
        return None
    ruta = resolver_ruta_csv(ruta)
    print(Intrucciones_bot())
    correcto, mensaje = valida_estructura(ruta) if valida_archivo(ruta) else (False, "No se encontró Calculo_KPIs.csv.")
    if not correcto:
        print(mensaje)
        if carga_archivo(ruta, colab) is None:
            print("Carga cancelada.")
            return None
    bot = BotKPIs(ruta)
    print("\n" + saludo_inicial())
    while not bot.terminado:
        try:
            texto = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + despedida_bot())
            break
        if not texto:
            continue
        if identificar_intencion(texto)["accion"] == "cargar":
            if carga_archivo(ruta, colab):
                bot = BotKPIs(ruta)
                print("Base actualizada.")
            continue
        print("\nBot: " + bot.responder(texto))
    return bot


def main():
    """Permite iniciar una conversación o ejecutar una consulta desde la terminal."""
    parser = argparse.ArgumentParser(description="Bot de KPIs NOC basado en reglas")
    parser.add_argument("--archivo", type=Path, help="Ruta del CSV; por defecto, junto al programa")
    parser.add_argument("--pregunta", help="Realiza una consulta y termina")
    args = parser.parse_args()
    try:
        if args.pregunta:
            print(BotKPIs(args.archivo).responder(args.pregunta))
        else:
            ejecutar(args.archivo)
    except (ValueError, OSError, RuntimeError) as e:
        parser.exit(1, str(e) + "\n")


if __name__ == "__main__":
    main()
