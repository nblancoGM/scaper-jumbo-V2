"""
Script de scraping para obtener el precio por kilogramo de productos en Jumbo
utilizando la API de ScrapingAnt.

Esta versión evita problemas de bloqueo de IP y detección de bots al delegar
la obtención del HTML a ScrapingAnt, un servicio de scraping con rotación
de proxies y renderizado de JavaScript. El script recupera el HTML renderizado
de cada página de producto y extrae el precio por kilo a partir del texto que
incluye "x kg". Luego actualiza una hoja de cálculo de Google Sheets con los
precios y la fecha de actualización.

Requisitos:

* Definir la variable de entorno ``GSPREAD_CREDENTIALS`` con el JSON de
  credenciales de Google Service Account (o disponer de ``credentials.json`` en
  la raíz del proyecto).
* Definir la variable de entorno ``SCRAPINGANT_API_KEY`` con la clave de API
  proporcionada por ScrapingAnt. Puedes obtener una clave gratuita con
  10.000 créditos mensuales registrándote en su portal【902417232907334†L309-L312】.

Dependencias:

* requests
* beautifulsoup4
* gspread
* google-auth-oauthlib
* pandas

Cómo funciona:

1. Lee la hoja "Jumbo-info" de la hoja de cálculo "Precios GM".
2. Para cada URL en la columna "URL", solicita el HTML renderizado de la
   página al endpoint ``/v2/general`` de ScrapingAnt.
3. Busca el ``<span>`` que contiene "x kg" y extrae el valor numérico entre
   paréntesis para obtener el precio por kilo.
4. Actualiza el DataFrame con el precio encontrado o "ERROR" si no se pudo
   obtener. También actualiza la fecha de última actualización.
5. Sobrescribe la hoja de cálculo con el DataFrame actualizado.

Al ejecutarse en GitHub Actions, asegúrate de configurar los secretos
``GSPREAD_CREDENTIALS`` y ``SCRAPINGANT_API_KEY``.
"""

import gspread
import pandas as pd
import re
import time
import os
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime


def obtener_precio_por_kilo(url_producto: str) -> int | None:
    """Obtiene el precio por kilo de un producto de Jumbo usando ScrapingAnt.

    Esta función construye una solicitud a la API de ScrapingAnt para recuperar
    el HTML renderizado de la página de producto de Jumbo. Utiliza ``browser=true``
    para ejecutar JavaScript y ``wait_for`` para dar tiempo al cargado de
    contenido dinámico. Luego analiza el HTML para extraer el texto
    que contiene "x kg" y, a partir de ahí, el valor numérico dentro de
    paréntesis.

    Args:
        url_producto: URL del producto de Jumbo.

    Returns:
        Un entero con el precio por kilogramo o ``None`` si no se pudo
        extraer.
    """
    api_key = os.environ.get("SCRAPINGANT_API_KEY")
    if not api_key:
        raise ValueError(
            "La variable de entorno SCRAPINGANT_API_KEY no está definida."
        )

    base_api = "https://api.scrapingant.com/v2/general"

    for intento in range(1, 4):
        try:
            print(f"   -> Intento #{intento} para {url_producto}...")
            params = {
                "x-api-key": api_key,
                "url": url_producto,
                "browser": "true",
                "wait_for": "5000",
            }
            response = requests.get(base_api, params=params, timeout=60)
            status = response.status_code
            if status != 200:
                print(
                    f"   -> La API respondió con status {status}. "
                    "Reintentando en 5 segundos..."
                )
                time.sleep(5)
                continue
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            span = soup.find(
                "span",
                string=lambda t: isinstance(t, str) and "x kg" in t,
            )
            if span:
                match = re.search(r"\(([^\)]*)\)", span.text)
                if match:
                    numeros = re.findall(r"\d+", match.group(1))
                    if numeros:
                        precio_final = int("".join(numeros))
                        print(
                            f"   -> ¡Éxito! Precio encontrado: {precio_final}"
                        )
                        return precio_final
            print(
                "   -> Elemento de precio no encontrado o formato inesperado. "
                "Reintentando en 5 segundos..."
            )
        except Exception as e:
            print(f"   -> Error en el intento #{intento}: {e}")
        time.sleep(5)
    print(
        f"   -> No se pudo obtener el precio para {url_producto} después de 3 intentos."
    )
    return None


def main() -> None:
    """Ejecuta el scraping para todas las URL en la hoja de cálculo.

    1. Se autentica con Google Sheets usando ``GSPREAD_CREDENTIALS`` o un
       archivo ``credentials.json``.
    2. Lee la pestaña "Jumbo-info" de la hoja "Precios GM".
    3. Para cada URL, obtiene el precio por kilo mediante ``obtener_precio_por_kilo``.
    4. Actualiza el DataFrame con el precio y la fecha de última actualización.
    5. Escribe los datos de vuelta en la hoja de cálculo.
    """
    print("Iniciando el proceso de actualización de precios...")
    # Autenticación con Google Sheets
    if "GSPREAD_CREDENTIALS" in os.environ and os.environ["GSPREAD_CREDENTIALS"]:
        creds_json = json.loads(os.environ["GSPREAD_CREDENTIALS"])
        gc = gspread.service_account_from_dict(creds_json)
        print(
            "Autenticado con Google Sheets usando credenciales de GitHub Secrets."
        )
    else:
        # Fallback a archivo local
        gc = gspread.service_account(filename="credentials.json")
        print(
            "Autenticado con Google Sheets usando el archivo local 'credentials.json'."
        )

    # Abrir la hoja de cálculo y la pestaña
    spreadsheet = gc.open("Precios GM")
    worksheet = spreadsheet.worksheet("Jumbo-info")
    print(
        f"Abierta la hoja de cálculo '{spreadsheet.title}' y la pestaña '{worksheet.title}'."
    )

    # Convertir la hoja a DataFrame para manipularla más cómodamente
    df = pd.DataFrame(worksheet.get_all_records())
    if "URL" not in df.columns:
        print("ERROR: La hoja de cálculo debe tener una columna llamada 'URL'.")
        return

    # Recorrer cada fila
    for index, row in df.iterrows():
        url = row["URL"]
        if url:
            precio = obtener_precio_por_kilo(url)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if precio is not None:
                df.loc[index, "Precio x KG"] = precio
                df.loc[index, "Ultima Actualizacion"] = now_str
            else:
                df.loc[index, "Precio x KG"] = "ERROR"
                df.loc[index, "Ultima Actualizacion"] = now_str
            # Pausa pequeña para no saturar la API
            time.sleep(1)

    print("Proceso de scraping finalizado. Actualizando la hoja de cálculo...")
    # Borrar el contenido existente y actualizar con el DataFrame
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Hoja de cálculo actualizada con éxito!")


if __name__ == "__main__":
    main()
