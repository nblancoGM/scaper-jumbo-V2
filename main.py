import gspread
import pandas as pd
import re
import time
import os
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# Importar la excepción de Timeout para manejarla específicamente
from selenium.common.exceptions import TimeoutException

# --- FUNCIÓN DE SCRAPING MEJORADA ---
def obtener_precio_por_kilo(url_producto, index):
    print(f"--- Iniciando scraping para: {url_producto} ---")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    # Aumentar el tamaño de la ventana puede ayudar a evitar layouts móviles
    options.add_argument("window-size=1280,800")

    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url_producto)
        
        # Aumentamos el tiempo de espera a 30 segundos
        wait = WebDriverWait(driver, 30)
        precio_element = wait.until(
            EC.visibility_of_element_located((By.XPATH, "//span[contains(text(), 'x kg')]"))
        )
        texto_precio = precio_element.text
        match = re.search(r'\((.*?)\)', texto_precio)
        if match:
            texto_precio_kg = match.group(1)
            numeros = re.findall(r'\d+', texto_precio_kg)
            if numeros:
                precio_final = int("".join(numeros))
                print(f"   -> Precio encontrado: {precio_final}")
                return precio_final
        return None
    
    except TimeoutException:
        print("   -> ERROR: Timeout. El elemento del precio no apareció en 30 segundos.")
        # **NUEVO**: Guardar captura de pantalla si hay un error de timeout
        screenshot_path = f"error_screenshot_{index}.png"
        driver.save_screenshot(screenshot_path)
        print(f"   -> Captura de pantalla guardada en: {screenshot_path}")
        return None

    except Exception as e:
        print(f"   -> ERROR al scrapear: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# --- FUNCIÓN PRINCIPAL (CON PEQUEÑO CAMBIO) ---
def main():
    print("Iniciando el proceso de actualización de precios...")
    
    if 'GSPREAD_CREDENTIALS' in os.environ:
        creds_json = json.loads(os.environ['GSPREAD_CREDENTIALS'])
        gc = gspread.service_account_from_dict(creds_json)
        print("Autenticado con Google Sheets usando credenciales de GitHub Secrets.")
    else:
        gc = gspread.service_account(filename='credentials.json')
        print("Autenticado con Google Sheets usando el archivo local 'credentials.json'.")

    spreadsheet = gc.open("Precios GM") 
    worksheet = spreadsheet.worksheet("Jumbo-info") 
    print(f"Abierta la hoja de cálculo '{spreadsheet.title}' y la pestaña '{worksheet.title}'.")

    df = pd.DataFrame(worksheet.get_all_records())
    
    if 'URL' not in df.columns:
        print("ERROR: La hoja de cálculo debe tener una columna llamada 'URL'.")
        return

    for index, row in df.iterrows():
        url = row['URL']
        if url:
            # Pasamos el 'index' para nombrar la captura de pantalla si falla
            precio = obtener_precio_por_kilo(url, index)
            if precio is not None:
                df.loc[index, 'Precio x KG'] = precio
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                df.loc[index, 'Precio x KG'] = "ERROR"
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            time.sleep(2) 

    print("Proceso de scraping finalizado. Actualizando la hoja de cálculo...")
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Hoja de cálculo actualizada con éxito!")

if __name__ == '__main__':
    main()
