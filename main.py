"""
Versión mejorada del script de scraping para Jumbo.

Esta versión implementa varias técnicas para reducir la probabilidad de que la página
usted detecte un navegador automatizado. Utiliza `undetected_chromedriver` para arrancar
Chrome en modo "stealth" y aplica configuraciones adicionales que imitan
mejor a un usuario real. También rota aleatoriamente el User‑Agent entre una
lista de navegadores modernos. Se mantienen intactas las funciones de lectura y
actualización de la hoja de cálculo Google Sheets.

Para utilizar este script en GitHub Actions debes instalar las dependencias
adicionales en tu workflow (`undetected-chromedriver`) y asegurarte de que
Google Chrome está disponible en el runner. Consulta el archivo
`.github/workflows/main.yml` para ver un ejemplo de instalación.
"""

import gspread
import pandas as pd
import re
import time
import os
import json
import random
from datetime import datetime

# Importamos undetected_chromedriver en lugar de webdriver_manager.
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Lista de user‑agents modernos para rotar aleatoriamente.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_6_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]


def obtener_precio_por_kilo(url_producto: str, index: int):
    """Obtiene el precio por kilo para un producto en Jumbo.

    Esta función navega hasta la URL del producto, espera a que aparezca el
    elemento de precio que contiene "x kg" y extrae el valor numérico. En
    caso de fallo, reintenta la operación hasta 3 veces. Utiliza
    `undetected_chromedriver` con opciones que reducen la detección.

    Args:
        url_producto: URL del producto de Jumbo a scrapear.
        index: Índice del producto en el DataFrame; se utiliza para
            nombrar las capturas de pantalla en caso de error.

    Returns:
        Un entero con el precio por kilogramo o `None` si no se puede
        extraer.
    """
    print(f"--- Iniciando scraping para: {url_producto} ---")

    options = uc.ChromeOptions()
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--window-size=1280,800")

    driver = None
    for intento in range(1, 4):
        try:
            print(f"   -> Intento #{intento}...")
            if driver is None:
                driver = uc.Chrome(options=options)
                # Ejecutamos scripts para enmascarar la automatización.
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
""",
                    },
                )

            driver.get(url_producto)

            wait = WebDriverWait(driver, 25)
            precio_element = wait.until(
                EC.visibility_of_element_located((By.XPATH, "//span[contains(text(), 'x kg')]"))
            )

            texto_precio = precio_element.text
            match = re.search(r"\((.*?)\)", texto_precio)
            if match:
                texto_precio_kg = match.group(1)
                numeros = re.findall(r"\d+", texto_precio_kg)
                if numeros:
                    precio_final = int("".join(numeros))
                    print(
                        f"   -> ¡Éxito en el intento #{intento}! Precio encontrado: {precio_final}"
                    )
                    driver.quit()
                    return precio_final

            print("   -> Elemento encontrado pero formato de precio incorrecto.")
            break

        except TimeoutException:
            print("   -> Timeout. El elemento del precio no apareció.")
            try:
                reintentar_button = driver.find_element(
                    By.XPATH, "//button[contains(text(), 'REINTENTAR')]"
                )
                print(
                    "   -> Botón 'REINTENTAR' encontrado. Haciendo clic y esperando..."
                )
                reintentar_button.click()
                time.sleep(5)
            except NoSuchElementException:
                print(
                    "   -> No se encontró el botón 'REINTENTAR'. Rindiéndose para esta URL."
                )
                break

        except Exception as e:
            print(f"   -> ERROR inesperado en el intento #{intento}: {e}")
            time.sleep(5)

    print(
        f"   -> No se pudo obtener el precio para {url_producto} después de 3 intentos."
    )
    if driver:
        screenshot_path = f"error_screenshot_{index}.png"
        driver.save_screenshot(screenshot_path)
        print(
            f"   -> Captura de pantalla final guardada en: {screenshot_path}"
        )
        driver.quit()
    return None


def main():
    """Ejecuta el scraping para todas las URL presentes en la hoja de cálculo.

    Este flujo abre la hoja "Precios GM", lee la pestaña "Jumbo-info" en un
    DataFrame de pandas y recorre cada fila llamando a `obtener_precio_por_kilo`.
    Después actualiza los datos de precio y la fecha de última actualización en
    la misma hoja. Si no se encuentran credenciales en la variable de entorno
    `GSPREAD_CREDENTIALS`, se utiliza un archivo local `credentials.json`.
    """
    print("Iniciando el proceso de actualización de precios...")

    if 'GSPREAD_CREDENTIALS' in os.environ and os.environ['GSPREAD_CREDENTIALS']:
        creds_json = json.loads(os.environ['GSPREAD_CREDENTIALS'])
        gc = gspread.service_account_from_dict(creds_json)
        print(
            "Autenticado con Google Sheets usando credenciales de GitHub Secrets."
        )
    else:
        gc = gspread.service_account(filename='credentials.json')
        print("Autenticado con Google Sheets usando el archivo local 'credentials.json'.")

    spreadsheet = gc.open("Precios GM")
    worksheet = spreadsheet.worksheet("Jumbo-info")
    print(
        f"Abierta la hoja de cálculo '{spreadsheet.title}' y la pestaña '{worksheet.title}'."
    )

    df = pd.DataFrame(worksheet.get_all_records())
    if 'URL' not in df.columns:
        print("ERROR: La hoja de cálculo debe tener una columna llamada 'URL'.")
        return

    for index, row in df.iterrows():
        url = row['URL']
        if url:
            precio = obtener_precio_por_kilo(url, index)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if precio is not None:
                df.loc[index, 'Precio x KG'] = precio
                df.loc[index, 'Ultima Actualizacion'] = now_str
            else:
                df.loc[index, 'Precio x KG'] = "ERROR"
                df.loc[index, 'Ultima Actualizacion'] = now_str
            time.sleep(random.uniform(1.5, 3.0))

    print("Proceso de scraping finalizado. Actualizando la hoja de cálculo...")
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Hoja de cálculo actualizada con éxito!")


if __name__ == '__main__':
    main()
